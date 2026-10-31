"""Shopify GraphQL integration. No mutations are retried automatically."""
import hashlib, json, re, time
from pathlib import Path
import requests

API_VERSION='2026-07'
SEARCH='''query Search($q: String!) { products(first: 30, query: $q) { nodes { id title handle } } }'''
PRODUCT='''query Product($id: ID!, $cursor: String) { product(id: $id) { id title media(first: 100, after: $cursor) { nodes { id alt status } pageInfo { hasNextPage endCursor } } } }'''
STAGE='''mutation Stage($input: [StagedUploadInput!]!) { stagedUploadsCreate(input: $input) { stagedTargets { url resourceUrl parameters { name value } } userErrors { field message } } }'''
ATTACH='''mutation Attach($product: ProductUpdateInput!, $media: [CreateMediaInput!]) { productUpdate(product: $product, media: $media) { product { id } userErrors { field message } } }'''
REORDER='''mutation Reorder($id: ID!, $moves: [MoveInput!]!) { productReorderMedia(id: $id, moves: $moves) { job { id done } mediaUserErrors { field message } } }'''
JOB='''query Job($id: ID!) { job(id: $id) { id done } }'''
class Shopify:
    def __init__(self,shop,token):
        shop=shop.strip().lower().removeprefix('https://').rstrip('/')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',shop): raise ValueError('Use the store’s permanent name.myshopify.com domain.')
        if not token.strip(): raise ValueError('Enter a Shopify Admin API access token.')
        self.shop=shop; self.token=token.strip()
    def gql(self,query,variables):
        try:
            r=requests.post(f'https://{self.shop}/admin/api/{API_VERSION}/graphql.json',headers={'X-Shopify-Access-Token':self.token},json={'query':query,'variables':variables},timeout=90)
        except requests.RequestException:
            raise RuntimeError('Shopify connection interrupted. A write may have completed; check the product before retrying.') from None
        if not r.ok: raise RuntimeError(f'Shopify HTTP {r.status_code}. Check token, store domain and API permissions.')
        data=r.json()
        if data.get('errors'): raise RuntimeError('Shopify: '+'; '.join(e['message'] for e in data['errors']))
        return data['data']
    @staticmethod
    def check(payload):
        errors=payload.get('userErrors',[])+payload.get('mediaUserErrors',[])
        if errors: raise RuntimeError('; '.join(e['message'] for e in errors))
        return payload
    def search(self,q): return self.gql(SEARCH,{'q':q})['products']['nodes']
    def media(self,pid):
        all_media=[]; cursor=None; title=''
        while True:
            p=self.gql(PRODUCT,{'id':pid,'cursor':cursor})['product']
            if not p: raise ValueError('Product was deleted or is inaccessible.')
            title=p['title']; m=p['media']; all_media.extend(m['nodes'])
            if not m['pageInfo']['hasNextPage']: return title,all_media
            cursor=m['pageInfo']['endCursor']
    def upload(self,pid,images,state_path,log):
        state_path=Path(state_path)
        state=json.loads(state_path.read_text()) if state_path.exists() else {}
        title,existing=self.media(pid); media_ids={m['id'] for m in existing}
        ids=[]; pending=[]
        # Duplicate prevention uses the local success ledger, scoped to store/product/content/alt.
        for im in images:
            path=Path(im['file']); digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest!=im['sha256']: raise ValueError('An exported file changed. Export again before upload.')
            key=hashlib.sha256((self.shop+pid+digest+im['alt']).encode()).hexdigest()
            saved=state.get(key)
            if saved and saved['id'] in media_ids:
                found=next(m for m in existing if m['id']==saved['id'])
                if found['status']=='FAILED': raise RuntimeError('Previously uploaded image failed Shopify processing. Check product media before retrying.')
                log('Already uploaded: '+path.name); ids.append(saved['id']); continue
            # Refuse ambiguous reattachment after interrupted writes; user checks Shopify.
            conflicts=[m for m in existing if m['alt']==im['alt']]
            if conflicts: raise RuntimeError(f'An existing image has alt text "{im["alt"]}". Check Shopify before retrying, or change the view label and re-export.')
            target=self.check(self.gql(STAGE,{'input':[{'filename':path.name,'mimeType':'image/jpeg' if path.suffix.lower()=='.jpg' else 'image/png','resource':'PRODUCT_IMAGE','httpMethod':'POST'}]})['stagedUploadsCreate'])['stagedTargets'][0]
            with path.open('rb') as f:
                try:
                    r=requests.post(target['url'],data=[(p['name'],p['value']) for p in target['parameters']],files={'file':(path.name,f,'image/jpeg' if path.suffix=='.jpg' else 'image/png')},timeout=120)
                except requests.RequestException: raise RuntimeError('Staged file transfer failed. No image was attached for this file.') from None
                if not r.ok: raise RuntimeError(f'Staged transfer failed: HTTP {r.status_code}.')
            before={m['id'] for m in existing}
            self.check(self.gql(ATTACH,{'product':{'id':pid},'media':[{'originalSource':target['resourceUrl'],'mediaContentType':'IMAGE','alt':im['alt']}]})['productUpdate'])
            for _ in range(15):
                _,existing=self.media(pid)
                new=[m for m in existing if m['id'] not in before and m['alt']==im['alt']]
                if new: break
                time.sleep(2)
            if len(new)!=1: raise RuntimeError('Could not identify attached image. Check Shopify before retrying; upload stopped.')
            mid=new[0]['id']; ids.append(mid)
            state[key]={'id':mid,'product':pid,'file':path.name}
            temp=state_path.with_suffix('.tmp'); temp.write_text(json.dumps(state,indent=2)); temp.replace(state_path)
            log('Attached: '+path.name)
        for _ in range(30):
            _,existing=self.media(pid); statuses={m['id']:m['status'] for m in existing}
            if any(statuses.get(mid)=='FAILED' for mid in ids): raise RuntimeError('Shopify could not process an uploaded image. Check the product media.')
            if all(statuses.get(mid)=='READY' for mid in ids): break
            time.sleep(2)
        else: raise RuntimeError('Images are attached but still processing. Re-run upload later to check and order them; ledger prevents duplicates.')
        job=self.check(self.gql(REORDER,{'id':pid,'moves':[{'id':mid,'newPosition':str(i)} for i,mid in enumerate(ids)]})['productReorderMedia'])['job']
        if job:
            for _ in range(30):
                if self.gql(JOB,{'id':job['id']})['job']['done']: break
                time.sleep(2)
            else: raise RuntimeError('Uploaded successfully; ordering is still pending. Check Shopify.')
        _,final=self.media(pid)
        expected={mid:im['alt'] for mid,im in zip(ids,images)}
        if any(m['alt']!=expected[m['id']] for m in final if m['id'] in expected): raise RuntimeError('Images attached, but alt-text verification failed. Check Shopify.')
        if [m['id'] for m in final[:len(ids)]]!=ids: raise RuntimeError('Images uploaded, but order verification failed. Check product media.')
        log(f'Verified {len(ids)} images on {title}. Existing photos retained after this batch.')


def request_access_token(shop,client_id,client_secret):
    client=Shopify(shop,'placeholder')
    if not client_id.strip() or not client_secret.strip(): raise ValueError('Enter the app Client ID and Client Secret.')
    try:
        r=requests.post(f'https://{client.shop}/admin/oauth/access_token',data={'grant_type':'client_credentials','client_id':client_id.strip(),'client_secret':client_secret.strip()},timeout=45)
    except requests.RequestException: raise RuntimeError('Could not connect to Shopify token endpoint.') from None
    if not r.ok: raise RuntimeError(f'Token request failed (HTTP {r.status_code}). Install the app first; app and store must belong to the same Shopify organization.')
    return r.json()['access_token']
