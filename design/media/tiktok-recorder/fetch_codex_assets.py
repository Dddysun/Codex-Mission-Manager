#!/usr/bin/env python3
"""Fetch the public OpenAI figures used by the Codex supplemental shots."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

PAGE='https://developers.openai.com/blog/run-long-horizon-tasks-with-codex'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for number in [4,5,6]:
        url='https://developers.openai.com/images/blog/long-horizon-'+str(number)+'.jpeg'
        request=urllib.request.Request(url,headers={'User-Agent':'TokenMax-media-recorder'})
        with urllib.request.urlopen(request,timeout=30) as response:
            data=response.read(8*1024*1024+1)
        if len(data)>8*1024*1024 or not data.startswith(b'\xff\xd8'):
            raise ValueError('Expected a bounded JPEG from the official source')
        path=args.output/(str(number)+'.jpeg')
        path.write_bytes(data)
        records.append({'file':path.name,'source':url,'page':PAGE,
                        'sha256':hashlib.sha256(data).hexdigest()})
    (args.output/'sources.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'official_public_images':len(records)}))


if __name__=='__main__':
    main()
