# -*- coding: utf-8 -*-
"""可编辑 PPT 预览服务。

用法:  python server_editable.py [port]   (默认 8124)
- GET  /train-marl-talk.html        返回注入"编辑工具栏"的版本(不写源文件)
- GET  /train-marl-talk/assets/*    静态图片
- POST ?file=...&save=1            把 body 传回的完整 HTML 覆盖写回当前 PPT 文件
- POST ?file=...&save=2            把当前 HTML 另存为一份带时间戳的副本

仅本机演示用:写入目标被白名单固定到 train-marl-talk/train-marl-talk.html
(或由 save=2 派生副本名),不接受任意路径,避免目录穿越。
"""
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DIR = os.path.dirname(os.path.abspath(__file__))
PPT_DIR = os.path.join(DIR, "train-marl-talk")
PPT_FILE = os.path.join(PPT_DIR, "train-marl-talk.html")

EDITOR = """\n<!-- ==== 可编辑预览工具栏(仅预览注入,不写源文件) ==== -->
<style class="edx">#edBar{position:fixed;right:14px;bottom:14px;z-index:99999;display:flex;gap:8px;align-items:center;background:#2b2b28;color:#fff;padding:6px 8px 6px 14px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.3);font:400 13px/1 system-ui,#Hei,Roboto,sans-serif}
#edBar b{font-weight:600}
#edBar button{border:0;border-radius:999px;padding:7px 14px;background:#c97a3d;color:#fff;cursor:pointer;font:600 13px/1 system-ui}
#edBar button.sec{background:#6d6c66}
#edTip{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:99999;background:#141413;color:#fff;padding:9px 18px;border-radius:999px;font:400 13px/1 system-ui;display:none;box-shadow:0 4px 14px rgba(0,0,0,.3)}
body.ized *{caret-color:#c97a3d!important}</style>
<div id="edTip" class="edx"></div>
<div id="edBar" class="edx" contenteditable="false"><b>可编辑预览</b>
<button id="edGo">✎ 编辑</button>
<button id="edSave" class="sec" style="display:none">保存回文件</button>
<button id="edCopy" style="display:none">导出副本</button>
</div>
<script class="edx">(function(){
var bar=document.getElementById('edBar'),go=document.getElementById('edGo'),sv=document.getElementById('edSave'),cp=document.getElementById('edCopy'),tip=document.getElementById('edTip');
var editing=false;
function t(m){tip.textContent=m;tip.style.display='block';clearTimeout(t._t);t._t=setTimeout(function(){tip.style.display='none'},2600);}
function setMode(on){
  editing=on;
  if(on){document.body.contentEditable=true;document.body.classList.add('ized');go.textContent='✕ 结束';sv.style.display='inline-flex';cp.style.display='inline-flex';t('编辑模式：鼠标点文字即可改，改完点保存');}
  else{document.body.className=document.body.className.replace(/\\bized\\b/g,'').replace(/\\s+/g,' ');document.body.removeAttribute('contenteditable');go.textContent='✎ 编辑';sv.style.display='none';cp.style.display='none';t('已退出编辑');}
}
function ser(){
  var el=document.querySelectorAll('.edx'),ref=[];
  el.forEach(function(e){ref.push([e.parentNode,e.nextSibling,e]);e.remove();});
  var body=document.body,was=editing;
  if(body.isContentEditable)body.removeAttribute('contenteditable');
  var s='<!DOCTYPE html>'+document.documentElement.outerHTML;
  ref.forEach(function(r){r[0].insertBefore(r[2],r[1]);});
  if(was)body.contentEditable=true;
  return s;
}
function save(copy){
  fetch('?file='+encodeURIComponent('train-marl-talk/train-marl-talk.html')+'&save='+(copy?2:1),
        {method:'POST',body:ser()})
   .then(function(r){return r.text()})
   .then(function(d){t(copy?'已导出副本: '+d:'已保存: '+d);})
   .catch(function(e){t('保存失败 '+e);});
}
go.addEventListener('click',function(){setMode(!editing);});
sv.addEventListener('click',function(){save(false);});
cp.addEventListener('click',function(){save(true);});
setMode(false);
})();</script>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path.startswith("/train-marl-talk.html"):
                with open(PPT_FILE, "r", encoding="utf-8") as f:
                    html = f.read()
                if "</body>" in html:
                    html = re.sub(r"(?i)(</body>)", EDITOR + "\\1", html, count=1)
                data = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            return self._static()
        except Exception as ex:
            import traceback
            traceback.print_exc()
            try:
                self._txt(500, "GET err: %s" % ex)
            except Exception:
                pass

    def _static(self):
        path = urlparse(self.path).path.lstrip("/")
        full = os.path.normpath(os.path.join(DIR, path.replace("/", os.sep)))
        if not full.startswith(DIR) or not os.path.isfile(full):
            self._txt(404, "not found"); return
        ext = os.path.splitext(full)[1].lower()
        ctype = {"png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml",
                 "css": "text/css", "js": "text/javascript"}.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        q = parse_qs(urlparse(self.path).query)
        save_mode = int((q.get("save") or ["1"])[0])
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        if save_mode == 2:
            ts = time.strftime("%Y%m%d_%H%M%S")
            out = os.path.join(PPT_DIR, "train-marl-talk_edited_%s.html" % ts)
            with open(out, "w", encoding="utf-8") as f:
                f.write(body)
            self._txt(200, "train-marl-talk_edited_%s.html" % ts)
        else:
            tmp = PPT_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, PPT_FILE)
            self._txt(200, "train-marl-talk.html")
        if "js" in content_type or True:
            pass  # 无鉴权回调,本机工具

    def _txt(self, code, msg):
        data = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("[ed-ppt] %s\n" % (fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    HTTPServer(("127.0.0.1", port), H).serve_forever()