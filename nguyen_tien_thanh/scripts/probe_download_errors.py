"""Inspect only recorded failed version URLs; optional HEAD probes never download a corpus."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--online',action='store_true',help='perform paced HEAD requests against the recorded failed URLs')
    ap.add_argument('--output',type=Path,default=ROOT/'audit_data/download_probe.json')
    args=ap.parse_args()
    status=json.loads((ROOT/'data/download_status.json').read_text(encoding='utf-8'))
    errors={k:v for k,v in status.items() if v.get('status')=='error'}
    if not args.online:
        print(json.dumps({'mode':'offline; no requests performed','failed_versions':list(errors)},indent=2));return
    import requests
    observations=[]
    with requests.Session() as session:
        session.headers['User-Agent']='hcmus-arxiv-source-audit/1.0 (targeted HEAD diagnostics)'
        blocked=0
        for key,info in errors.items():
            row={'version':key,'historical_http':info.get('http'),'method':'HEAD','observed_at':datetime.now(timezone.utc).isoformat()}
            # Construct from the ID rather than trusting URLs in local JSON.
            url=f'https://export.arxiv.org/src/{key}'
            try:
                response=session.head(url,allow_redirects=True,timeout=30)
                row.update(http=response.status_code,final_url=response.url,
                           content_type=response.headers.get('Content-Type'))
                blocked=blocked+1 if response.status_code in (403,429) else 0
            except requests.RequestException as error:
                row.update(http=None,error=type(error).__name__)
                observations.append(row)
                print(key,row.get('error'),flush=True)
                break  # connectivity failure is not a per-version source failure
            observations.append(row);print(key,row['http'],flush=True)
            if blocked>=1:break
            time.sleep(3)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'scope':'targeted HEAD only; no source bodies downloaded or historical statuses changed',
                                     'historical_failed_count':len(errors),'observations':observations,
                                     'limitation':'HEAD may differ from GET; blocked/network outcomes do not prove source absence'},indent=2),encoding='utf-8')

if __name__=='__main__':main()
