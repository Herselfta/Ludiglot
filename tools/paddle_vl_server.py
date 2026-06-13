import http.server
import json
import base64
import io
import os
import shutil
import tempfile
import ssl
from pathlib import Path
from PIL import Image

# 禁用全局 SSL 证书验证，绕过百度 CDN (gitea-cdn.baidu-tech.com) 证书过期的 bug
ssl._create_default_https_context = ssl._create_unverified_context
os.environ["PYTHONHTTPSVERIFY"] = "0"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["FLAGS_enable_pir_api"] = "0"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
_orig_request = requests.Session.request
def _patched_request(self, method, url, *args, **kwargs):
    kwargs['verify'] = False
    return _orig_request(self, method, url, *args, **kwargs)
requests.Session.request = _patched_request

# 禁用星河社区 (AiStudio) SDK 的 CDN 重定向，强制从主站稳定下载以绕过 504 错误
try:
    import aistudio_sdk.switch_downoad
    aistudio_sdk.switch_downoad.switch_cdn = lambda url, headers, get_headers: url
except ImportError:
    pass

# Global pipeline instance
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        print("[Server] 正在加载 PaddleOCR-VL-1.6 模型 (这可能需要几分钟，首次运行会自动下载模型权重)...")
        import paddle
        try:
            paddle.set_flags({'FLAGS_enable_pir_api': 0})
        except Exception as e:
            print(f"[Server] 设置 FLAGS_enable_pir_api 失败: {e}")
        from paddleocr import PaddleOCRVL
        # 默认加载 v1 管道
        pipeline = PaddleOCRVL(pipeline_version="v1")
        print("[Server] PaddleOCR-VL 模型加载成功！")
    return pipeline

class PaddleVLRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress standard logging to keep console clean
        pass

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            req_data = json.loads(body.decode('utf-8'))
        except Exception as e:
            self.send_error(400, f"Invalid JSON: {e}")
            return

        # Find base64 image in OpenAI chat payload
        image_b64 = None
        messages = req_data.get("messages", [])
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        img_url_data = item.get("image_url", {})
                        url = img_url_data.get("url", "")
                        if url.startswith("data:image"):
                            # Format: data:image/png;base64,...
                            image_b64 = url.split(",")[1]
                            break

        if not image_b64:
            print("[Server] 请求中未发现有效的 image_url")
            self._send_json({"choices": [{"message": {"role": "assistant", "content": ""}}]})
            return

        try:
            # Decode base64 image and save to a temporary file
            image_bytes = base64.b64decode(image_b64)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                img_path = Path(tmpdir) / "input.png"
                img_path.write_bytes(image_bytes)
                
                # Predict
                pipe = get_pipeline()
                print("[Server] 正在使用 PaddleOCR-VL 识别图像...")
                output = pipe.predict(
                    str(img_path),
                    use_layout_detection=False,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_chart_recognition=False,
                    use_seal_recognition=False,
                    use_ocr_for_image_block=False,
                    use_queues=False,
                    max_new_tokens=150,
                    min_pixels=50176,
                    max_pixels=200704
                )
                
                # Extract markdown text using temp directory
                markdown_texts = []
                out_dir = Path(tmpdir) / "output"
                out_dir.mkdir(exist_ok=True)
                
                for res in output:
                    res.save_to_markdown(str(out_dir))
                
                # Read all generated .md files in the output directory
                for md_file in out_dir.glob("*.md"):
                    markdown_texts.append(md_file.read_text(encoding="utf-8"))
                
                full_text = "\n".join(markdown_texts)
                print(f"[Server] 识别成功，文本长度: {len(full_text)}")
                
                self._send_json({
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": full_text
                            }
                        }
                    ]
                })
        except Exception as e:
            print(f"[Server] 图像处理或识别失败: {e}")
            import traceback
            traceback.print_exc()
            if not isinstance(e, (ConnectionError, BrokenPipeError)):
                self._send_json({
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": f"识别错误: {e}"
                            }
                        }
                    ]
                })

    def _send_json(self, data):
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (ConnectionError, BrokenPipeError) as ce:
            print(f"[Server] 无法发送响应，客户端连接已断开: {ce}")
        except Exception as e:
            print(f"[Server] 发送 JSON 失败: {e}")

def run_server(port=8000):
    server_address = ('127.0.0.1', port)
    httpd = http.server.HTTPServer(server_address, PaddleVLRequestHandler)
    print(f"[Server] 本地 PaddleOCR-VL-1.6 API 服务已启动: http://127.0.0.1:{port}/v1")
    print("[Server] 请在 Ludiglot 设置中选择 PaddleOCR-VL 后端，并确保配置 API URL 为该地址。")
    print("[Server] 按 Ctrl+C 退出服务器...")
    try:
        # Pre-warm the model
        get_pipeline()
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] 正在关闭服务器...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
