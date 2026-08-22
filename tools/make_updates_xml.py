"""
自己ホスト配布用の更新マニフェスト(updates.xml)を作る。

Chromeは、ポリシーで指定されたこのXMLを定期的に読みに行き、そこに書かれた
versionが手元のものより新しければ、codebaseのURLから.crxを取得して自動更新する。

使い方:
  python3 tools/make_updates_xml.py <拡張機能ID> <配布URLのベース>

例:
  python3 tools/make_updates_xml.py abcdefghijklmnopabcdefghijklmnop https://ext.143-198-195-132.nip.io

manifest.json からバージョンを自動で読み取り、updates.xml を出力する。
"""
import json
import os
import sys

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

ext_id = sys.argv[1].strip()
base_url = sys.argv[2].strip().rstrip('/')

if len(ext_id) != 32 or not ext_id.isalpha() or not ext_id.islower():
    print(f'拡張機能IDの形式が正しくありません（英小文字32文字）: {ext_id}')
    sys.exit(1)

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(root, 'manifest.json'), encoding='utf-8') as f:
    version = json.load(f)['version']

xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='{ext_id}'>
    <updatecheck codebase='{base_url}/snowwe.crx' version='{version}' />
  </app>
</gupdate>
"""

out = os.path.join(root, 'updates.xml')
with open(out, 'w', encoding='utf-8') as f:
    f.write(xml)

print(f'updates.xml を作成しました（バージョン {version}）')
print(f'  配布URL: {base_url}/snowwe.crx')
