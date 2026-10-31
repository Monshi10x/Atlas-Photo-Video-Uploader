import io, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Settings, render, encode, export_batch, choose_local, clean_name
from shopify_api import Shopify
class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.photo=self.root/'photo.png';Image.new('RGB',(1000,500),'white').save(self.photo)
        self.logo=self.root/'logo.png';Image.new('RGBA',(100,50),(255,0,0,255)).save(self.logo)
        self.s=Settings(logo_path=str(self.logo),logo_width=20,logo_x=770,logo_y=385,output_dir=str(self.root/'exports'))
    def tearDown(self):self.temp.cleanup()
    def test_placement_and_opacity(self):
        im=render(self.photo,self.s)
        self.assertEqual(im.getpixel((969,484)),(255,0,0,255));self.assertEqual(im.getpixel((970,484)),(255,255,255,255))
        self.s.logo_x=30;self.s.logo_y=15;self.s.logo_opacity=50
        im=render(self.photo,self.s);self.assertEqual(im.getpixel((30,15))[:3],(255,127,127))
    def test_transparency_square_and_portrait_logo_fit(self):
        Image.new('RGBA',(120,120),(0,0,0,0)).save(self.photo)
        self.s.format='PNG';im=render(self.photo,self.s);self.assertEqual(im.getpixel((0,0))[3],0)
        self.s.square=True;im=render(self.photo,self.s);self.assertEqual(im.getpixel((0,0))[3],255)
        Image.new('RGBA',(2,1000),'red').save(self.logo);render(self.photo,self.s)
    def test_noise_reaches_size_cap(self):
        rng=np.random.default_rng(8);im=Image.fromarray(rng.integers(0,256,(1500,1500,4),dtype=np.uint8),'RGBA')
        self.s.max_mb=.12
        data,size=encode(im,self.s);self.assertLess(len(data),120000)
        self.s.format='PNG';data,size=encode(im,self.s);self.assertLess(len(data),120000)
    def test_export_unique_and_original_untouched(self):
        original=self.photo.read_bytes();rows=[(str(self.photo),'Main')]
        a=export_batch(rows,'Atlas Tools 8x22 ZrN',self.s);b=export_batch(rows,'Atlas Tools 8x22 ZrN',self.s)
        self.assertNotEqual(a[0]['file'],b[0]['file']);self.assertEqual(Path(a[0]['file']).stem,a[0]['alt']);self.assertEqual(original,self.photo.read_bytes())
    def test_long_names_do_not_overwrite_views(self):
        images=export_batch([(str(self.photo),'Main'),(str(self.photo),'Reverse')],'A'*200,self.s)
        self.assertNotEqual(images[0]['file'],images[1]['file'])
        self.assertTrue(all(Path(x['file']).is_file() for x in images))
    def test_duplicate_selection_and_windows_names(self):
        copy=self.root/'copy.png';copy.write_bytes(self.photo.read_bytes())
        result=choose_local([self.photo,copy]);self.assertEqual(len(result),1)
        self.assertEqual(clean_name('CON'),'Atlas CON');self.assertNotIn('/',clean_name('A/B'))
    def test_exif_rotation(self):
        p=self.root/'rotate.jpg';exif=Image.Exif();exif[274]=6
        Image.new('RGB',(500,100),'white').save(p,exif=exif)
        self.s.longest_edge=256;im=render(p,self.s);self.assertEqual(im.size,(51,256))
class ShopifyTests(unittest.TestCase):
    def test_no_wrong_domain(self):
        for host in ['example.com','foo.myshopify.com.evil.test','foo.myshopify.com/a','']:
            with self.assertRaises(ValueError):Shopify(host,'token')
    def test_graphql_user_errors(self):
        with self.assertRaisesRegex(RuntimeError,'Denied'):Shopify.check({'userErrors':[{'message':'Denied'}]})
    def test_existing_upload_skipped_and_ordered(self):
        with tempfile.TemporaryDirectory() as tmp:
            import hashlib
            p=Path(tmp)/'photo.jpg';p.write_bytes(b'photo');digest=hashlib.sha256(b'photo').hexdigest();client=Shopify('atlas.myshopify.com','test')
            pid='gid://shopify/Product/1';mid='gid://shopify/MediaImage/1';alt='Atlas - Main'
            key=hashlib.sha256((client.shop+pid+digest+alt).encode()).hexdigest();state=Path(tmp)/'ledger.json';state.write_text(json.dumps({key:{'id':mid}}))
            media=[{'id':mid,'alt':alt,'status':'READY'}];calls=[]
            def gql(q,v):
                calls.append(q);return {'productReorderMedia':{'job':None,'mediaUserErrors':[]}}
            with patch.object(client,'media',return_value=('Atlas',media)),patch.object(client,'gql',side_effect=gql):
                client.upload(pid,[{'file':str(p),'sha256':digest,'alt':alt}],state,lambda m:None)
            self.assertEqual(len(calls),1);self.assertIn('Reorder',calls[0])
    def test_full_staged_upload_records_verified_image(self):
        import hashlib
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'Atlas - Main.jpg';p.write_bytes(b'photo');client=Shopify('atlas.myshopify.com','test')
            mid='gid://shopify/MediaImage/9';media=[{'id':mid,'alt':'Atlas - Main','status':'READY'}]
            attached=[]
            def gql(query,variables):
                if 'mutation Stage' in query:
                    return {'stagedUploadsCreate':{'stagedTargets':[{'url':'https://upload.example.test','resourceUrl':'https://resource.example.test/photo','parameters':[{'name':'key','value':'upload-key'}]}],'userErrors':[]}}
                if 'mutation Attach' in query:
                    attached.append(variables);return {'productUpdate':{'userErrors':[],'product':{'id':'pid'}}}
                if 'mutation Reorder' in query:return {'productReorderMedia':{'job':None,'mediaUserErrors':[]}}
                self.fail('Unexpected operation')
            state=Path(tmp)/'ledger.json';item={'file':str(p),'alt':'Atlas - Main','sha256':hashlib.sha256(b'photo').hexdigest()}
            with patch.object(client,'media',side_effect=[('Atlas',[]),('Atlas',media),('Atlas',media),('Atlas',media)]),patch.object(client,'gql',side_effect=gql),patch('shopify_api.requests.post',return_value=Mock(ok=True)) as transfer:
                client.upload('pid',[item],state,lambda m:None)
            self.assertEqual(attached[0]['media'][0]['alt'],'Atlas - Main')
            self.assertEqual(next(iter(json.loads(state.read_text()).values()))['id'],mid)
            self.assertEqual(transfer.call_args.kwargs['files']['file'][0],p.name)
    def test_ambiguous_alt_stops_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            import hashlib
            p=Path(tmp)/'photo.jpg';p.write_bytes(b'photo');client=Shopify('atlas.myshopify.com','test')
            with patch.object(client,'media',return_value=('Atlas',[{'id':'old','alt':'Same','status':'READY'}])),patch.object(client,'gql') as gql:
                with self.assertRaisesRegex(RuntimeError,'existing image'):client.upload('pid',[{'file':str(p),'sha256':hashlib.sha256(b'photo').hexdigest(),'alt':'Same'}],Path(tmp)/'ledger.json',lambda m:None)
                gql.assert_not_called()
if __name__=='__main__':unittest.main()
