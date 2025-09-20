#!/usr/bin/env python3

import os
import sys
import time
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory, Response, send_file
import mimetypes
import io
import RNS
import RNS.vendor.umsgpack as msgpack
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # needed for flask sessions

class NomadNetBrowser:
    def __init__(self, main_browser, destination_hash):
        self.main_browser = main_browser
        clean_hash = destination_hash.replace("<", "").replace(">", "").replace(":", "")
        self.destination_hash = bytes.fromhex(clean_hash)

    def fetch_page(self, page_path="/page/index.mu", timeout=30):
        try:
            print(f"🔍 Checking path to {RNS.prettyhexrep(self.destination_hash)[:16]}...")
            
            if not RNS.Transport.has_path(self.destination_hash):
                print(f"📡 Requesting path to {RNS.prettyhexrep(self.destination_hash)[:16]}...")
                RNS.Transport.request_path(self.destination_hash)
                start_time = time.time()
                while not RNS.Transport.has_path(self.destination_hash):
                    if time.time() - start_time > 30:
                        return {"error": "No path", "content": "No path to destination", "status": "error"}
                    time.sleep(0.1)
            
            print(f"✅ Path found, establishing connection...")
            identity = RNS.Identity.recall(self.destination_hash)
            if not identity:
                return {"error": "No identity", "content": "Could not recall identity", "status": "error"}
            
            self.destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "nomadnetwork", "node")
            self.link = RNS.Link(self.destination)
            self.result = {"data": None, "received": False}
            self.response_event = threading.Event()
            self.page_path = page_path
            
            print(f"🌐 Requesting page: {page_path}")
            self.link.set_link_established_callback(self._on_link_established)
            success = self.response_event.wait(timeout=timeout)
            
            if success and self.result["received"]:
                return {"content": self.result["data"] or "Empty response", "status": "success", "error": None}
            else:
                return {"error": "Timeout", "content": "Request timeout", "status": "error"}
                
        except Exception as e:
            print(f"❌ Exception during fetch: {str(e)}")
            return {"error": str(e), "content": f"Exception: {str(e)}", "status": "error"}
    
    def _on_link_established(self, link):
        try:
            print(f"🔗 Link established, requesting: {self.page_path}")
            link.request(self.page_path, data=None, response_callback=self._on_response, failed_callback=self._on_request_failed)
        except Exception as e:
            print(f"❌ Request error: {str(e)}")
            self.result["data"] = f"Request error: {str(e)}"
            self.result["received"] = True
            self.response_event.set()
    
    def _on_response(self, receipt):
        try:
            if receipt.response:
                data = receipt.response
                if isinstance(data, bytes):
                    try:
                        self.result["data"] = data.decode("utf-8")
                        print(f"✅ Received {len(self.result['data'])} characters")
                    except UnicodeDecodeError:
                        self.result["data"] = f"Binary data: {data.hex()[:200]}..."
                        print(f"⚠️ Received binary data: {len(data)} bytes")
                else:
                    self.result["data"] = str(data)
                    print(f"✅ Received text data: {len(str(data))} characters")
            else:
                self.result["data"] = "Empty response"
                print("⚠️ Empty response received")
            self.result["received"] = True
            self.response_event.set()
        except Exception as e:
            print(f"❌ Response processing error: {str(e)}")
            self.result["data"] = f"Response error: {str(e)}"
            self.result["received"] = True
            self.response_event.set()
    
    def _on_request_failed(self, receipt):
        print("❌ Request failed")
        self.result["data"] = "Request failed"
        self.result["received"] = True
        self.response_event.set()

class NomadNetFileBrowser:
    def __init__(self, main_browser, destination_hash):
        self.main_browser = main_browser
        clean_hash = destination_hash.replace("<", "").replace(">", "").replace(":", "")
        self.destination_hash = bytes.fromhex(clean_hash)
        
    def fetch_file(self, file_path, timeout=60):  # Longer timeout for files
        try:
            print(f"🔍 Checking path to {RNS.prettyhexrep(self.destination_hash)[:16]} for file...")
            
            if not RNS.Transport.has_path(self.destination_hash):
                print(f"📡 Requesting path to {RNS.prettyhexrep(self.destination_hash)[:16]}...")
                RNS.Transport.request_path(self.destination_hash)
                start_time = time.time()
                while not RNS.Transport.has_path(self.destination_hash):
                    if time.time() - start_time > 30:
                        return {"error": "No path", "content": b"", "status": "error"}
                    time.sleep(0.1)
            
            print(f"✅ Path found, establishing connection for file transfer...")
            identity = RNS.Identity.recall(self.destination_hash)
            if not identity:
                return {"error": "No identity", "content": b"", "status": "error"}
            
            self.destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "nomadnetwork", "node")
            self.link = RNS.Link(self.destination)
            self.result = {"data": None, "received": False}
            self.response_event = threading.Event()
            self.file_path = file_path
            
            print(f"📁 Requesting file: {file_path}")
            self.link.set_link_established_callback(self._on_link_established)
            success = self.response_event.wait(timeout=timeout)
            
            if success and self.result["received"]:
                return {"content": self.result["data"] or b"", "status": "success", "error": None}
            else:
                return {"error": "Timeout", "content": b"", "status": "error"}
                
        except Exception as e:
            print(f"❌ Exception during file fetch: {str(e)}")
            return {"error": str(e), "content": b"", "status": "error"}
    
    def _on_link_established(self, link):
        try:
            print(f"🔗 Link established, requesting file: {self.file_path}")
            link.request(self.file_path, data=None, response_callback=self._on_response, failed_callback=self._on_request_failed)
        except Exception as e:
            print(f"❌ File request error: {str(e)}")
            self.result["data"] = b""
            self.result["received"] = True
            self.response_event.set()
    
    def _on_response(self, receipt):
        try:
            if receipt.response:
                data = receipt.response
                print(f"📁 Received response type: {type(data)}")
                print(f"📁 Response repr: {repr(data)}")
                
                if isinstance(data, bytes):
                    self.result["data"] = data
                    print(f"✅ Received file data: {len(data)} bytes")
                elif isinstance(data, str):
                    self.result["data"] = data.encode('utf-8')
                    print(f"✅ Received text file: {len(data)} characters")
                elif hasattr(data, 'read'):
                    # Handle file objects (_io.BufferedReader, etc.)
                    try:
                        print(f"📁 Reading file object: {data}")
                        
                        # Try to seek to beginning
                        if hasattr(data, 'seek'):
                            data.seek(0)
                            print(f"📁 Seeked to beginning")
                        
                        # Read the file content
                        file_content = data.read()
                        print(f"📁 Read {len(file_content)} bytes from file object")
                        
                        # Ensure we have bytes
                        if isinstance(file_content, bytes):
                            self.result["data"] = file_content
                        else:
                            self.result["data"] = str(file_content).encode('utf-8')
                        
                        print(f"✅ Successfully read file: {len(self.result['data'])} bytes")
                        
                        # Close the file if possible
                        if hasattr(data, 'close'):
                            data.close()
                            print(f"📁 Closed file object")
                            
                    except Exception as read_error:
                        print(f"❌ Error reading file object: {read_error}")
                        print(f"📁 File object details: {dir(data)}")
                        self.result["data"] = b""
                else:
                    print(f"❌ Unknown data type: {type(data)}")
                    self.result["data"] = b""
            else:
                self.result["data"] = b""
                print("⚠️ Empty file response received")
                
            self.result["received"] = True
            self.response_event.set()
        except Exception as e:
            print(f"❌ File response processing error: {str(e)}")
            self.result["data"] = b""
            self.result["received"] = True
            self.response_event.set()

    def _on_request_failed(self, receipt):
        print("❌ File request failed")
        self.result["data"] = b""
        self.result["received"] = True
        self.response_event.set()


class NomadNetAnnounceHandler:
    def __init__(self, browser):
        self.browser = browser
        self.aspect_filter = "nomadnetwork.node"
        
    def received_announce(self, destination_hash, announced_identity, app_data):
        self.browser.process_nomadnet_announce(destination_hash, announced_identity, app_data)

class NomadNetWebBrowser:
    def __init__(self):
        self.reticulum = None
        self.identity = None
        self.nomadnet_nodes = {}
        self.running = False
        self.announce_count = 0
        
        print("Initializing NomadNet Web Browser...")
        self.init_reticulum()
        
    def init_reticulum(self):
        try:
            RNS.loglevel = RNS.LOG_NOTICE
            self.reticulum = RNS.Reticulum()
            
            identity_path = "nomadnet_browser_identity"
            if os.path.exists(identity_path):
                self.identity = RNS.Identity.from_file(identity_path)
            else:
                self.identity = RNS.Identity()
                self.identity.to_file(identity_path)
            
            self.nomadnet_handler = NomadNetAnnounceHandler(self)
            RNS.Transport.register_announce_handler(self.nomadnet_handler)
            print(f"Browser identity: {RNS.prettyhexrep(self.identity.hash)}")
            
        except Exception as e:
            print(f"Failed to initialize: {e}")
            sys.exit(1)
    
    def process_nomadnet_announce(self, destination_hash, announced_identity, app_data):
        self.announce_count += 1
        hash_str = RNS.prettyhexrep(destination_hash)
        clean_hash_str = hash_str.replace("<", "").replace(">", "").replace(":", "")
        
        node_name = "UNKNOWN"
        if app_data:
            try:
                node_name = app_data.decode('utf-8')
            except:
                try:
                    decoded = msgpack.unpackb(app_data)
                    node_name = str(decoded) if isinstance(decoded, str) else f"Node_{hash_str[:8]}"
                except:
                    node_name = f"BinaryNode_{hash_str[:8]}"
        else:
            node_name = f"EmptyNode_{hash_str[:8]}"
        
        # Filter out test nodes
        if node_name.startswith("EmptyNode_") or node_name.startswith("BinaryNode_") or node_name == "UNKNOWN":
            print(f"Filtered test node: {hash_str[:16]} -> {node_name}")
            return
        
        self.nomadnet_nodes[hash_str] = {
            "hash": clean_hash_str,
            "name": node_name,
            "last_seen": datetime.now().isoformat(),
            "announce_count": self.announce_count,
            "app_data_length": len(app_data) if app_data else 0,
            "last_seen_relative": "Just now"
        }
        
        print(f"NomadNet #{self.announce_count}: {hash_str[:16]} -> {node_name}")
    
    def get_nodes(self):
        current_time = datetime.now()
        for node in self.nomadnet_nodes.values():
            last_seen = datetime.fromisoformat(node['last_seen'])
            diff = current_time - last_seen
            
            if diff.total_seconds() < 60:
                node['last_seen_relative'] = "Just now"
            elif diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                node['last_seen_relative'] = f"{minutes}m ago"
            else:
                hours = int(diff.total_seconds() / 3600)
                node['last_seen_relative'] = f"{hours}h ago"
        
        return list(self.nomadnet_nodes.values())
    
    def fetch_file(self, node_hash, file_path):
        """Fetch a file from a NomadNet node"""
        try:
            print(f"📁 NomadNetWebBrowser.fetch_file called: {file_path} from {node_hash[:16]}...")
            print(f"📁 Creating NomadNetFileBrowser instance...")
            browser = NomadNetFileBrowser(self, node_hash)
            response = browser.fetch_file(file_path)
            return response
        except Exception as e:
            print(f"❌ File fetch failed: {str(e)}")
            return {"error": f"File fetch failed: {str(e)}", "content": b"", "status": "error"}
                
    def fetch_page(self, node_hash, page_path="/page/index.mu"):
        try:
            print(f"🌐 Fetching {page_path} from {node_hash[:16]}...")
            browser = NomadNetBrowser(self, node_hash)
            response = browser.fetch_page(page_path)
            return response
        except Exception as e:
            print(f"❌ Fetch failed: {str(e)}")
            return {"error": f"Fetch failed: {str(e)}", "content": "", "status": "error"}
            
    def start_monitoring(self):
        self.running = True
        print("Started NomadNet announce monitoring")

# Initialize the browser
browser = NomadNetWebBrowser()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/style.css')
def serve_css():
    return send_from_directory('templates', 'style.css', mimetype='text/css')

@app.route('/api/nodes')
def api_nodes():
    return jsonify(browser.get_nodes())

@app.route('/api/status')
def api_status():
    return jsonify({
        "running": browser.running,
        "total_announces": browser.announce_count,
        "unique_nodes": len(browser.nomadnet_nodes),
        "identity_hash": RNS.prettyhexrep(browser.identity.hash) if browser.identity else None
    })

@app.route('/api/fetch/<node_hash>')
def api_fetch_page(node_hash):
    # Get the path parameter, default to /page/index.mu
    page_path = request.args.get('path', '/page/index.mu')
    
    print(f"🌐 API Request: Fetching {page_path} from {node_hash[:16]}...")
    response = browser.fetch_page(node_hash, page_path)
    
    if response["status"] == "success":
        content_length = len(response.get('content', ''))
        print(f"✅ API Response: Successfully fetched {content_length} characters")
    else:
        print(f"❌ API Response: Failed - {response.get('error', 'Unknown error')}")
    
    return jsonify(response)

@app.route('/script/purify.min.js')
def serve_purify():
    """Serve the DOMPurify library"""
    try:
        script_path = os.path.join('script', 'purify.min.js')
        if os.path.exists(script_path):
            print(f"✅ Serving DOMPurify from: {script_path}")
            return send_from_directory('script', 'purify.min.js', mimetype='application/javascript')
        else:
            print(f"❌ DOMPurify not found at: {script_path}")
            return "console.error('DOMPurify file not found');", 404
    except Exception as e:
        print(f"❌ Error serving DOMPurify: {e}")
        return f"console.error('Error loading DOMPurify: {str(e)}');", 500

@app.route('/script/micron-parser_original.js')
def serve_micron_parser():
    """Serve the modified micron parser script"""
    try:
        script_path = os.path.join('script', 'micron-parser_original.js')
        if os.path.exists(script_path):
            print(f"✅ Serving micron parser from: {script_path}")
            return send_from_directory('script', 'micron-parser_original.js', mimetype='application/javascript')
        else:
            print(f"❌ Micron parser not found at: {script_path}")
            return "console.error('Micron parser file not found');", 404
    except Exception as e:
        print(f"❌ Error serving micron parser: {e}")
        return f"console.error('Error loading micron parser: {str(e)}');", 500
    
@app.route('/api/download/<node_hash>')
def api_download_file(node_hash):
    """Download a file from a NomadNet node"""
    file_path = request.args.get('path', '/file/')
    
    if not file_path.startswith('/file/'):
        return jsonify({"error": "Invalid file path"}), 400
    
    print(f"📁 Download Request: {file_path} from {node_hash[:16]}...")
    
    try:
        # Fetch the file using the browser
        response = browser.fetch_file(node_hash, file_path)
        
        if response["status"] == "error":
            print(f"❌ Download failed: {response.get('error', 'Unknown error')}")
            return jsonify(response), 404
        
        # Get file content and metadata
        file_data = response["content"]
        filename = file_path.split('/')[-1] or "download"
        
        # Ensure file_data is bytes
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        elif not isinstance(file_data, bytes):
            file_data = str(file_data).encode('utf-8')
        
        # Check if we actually got data
        if not file_data:
            print(f"❌ No file data received")
            return jsonify({"error": "No file data received"}), 404
            
        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        print(f"✅ Serving file: {filename} ({len(file_data)} bytes, {mime_type})")
        
        # Create file-like object from bytes
        file_obj = io.BytesIO(file_data)
        
        return send_file(
            file_obj,
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"❌ Download exception: {str(e)}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/favicon.svg')
def favicon():
    return '', 204  # No content response


def start_server():
    """Automatically choose the best server available"""
    import platform
    
    # Try Waitress first on Windows
    if platform.system() == "Windows":
        try:
            from waitress import serve
            print("🚀 Starting with Waitress (Windows optimized)...")
            print("📡 Access logs disabled for cleaner output")
            serve(app, host='0.0.0.0', port=5000, threads=4)
            return
        except ImportError:
            pass
    
    # Try Gunicorn on Unix/Linux
    try:
        import gunicorn.app.wsgiapp as wsgi
        # Configure gunicorn to suppress access logs
        sys.argv = [
            'gunicorn',
            '--bind', '0.0.0.0:5000',
            '--workers', '4',
            '--access-logfile', '/dev/null',  # Disable access logs
            '--error-logfile', '-',           # Errors to stderr
            '--log-level', 'warning',         # Only warnings and errors
            f'{os.path.basename(__file__).split(".")[0]}:app'
        ]
        print("🚀 Starting with Gunicorn for optimal performance...")
        print("📡 Access logs disabled for cleaner output")
        wsgi.run()
        return
    except ImportError:
        pass
    
    # Fallback to Flask development server
    system_name = platform.system()
    if system_name == "Windows":
        print("⚠️  Waitress not found - using Flask development server")
        print("   For better performance on Windows: pip install waitress")
    else:
        print("⚠️  Gunicorn not found - using Flask development server")
        print("   For better performance: pip install gunicorn")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def main():
    print("=" * 70)
    print("🌐 rBrowser v1.0 - Standalone Nomadnet Browser")
    print("https://github.com/fr33n0w/rBrowser")
    print("=" * 70)
    
    # Check file structure
    template_path = os.path.join('templates', 'index.html')
    if os.path.exists(template_path):
        print(f"✅ Found HTML template: {template_path}")
    else:
        print(f"❌ HTML template not found: {template_path}")
        print("   Please verify templates/ directory and index.html file")
        return
    
    micron_path = os.path.join('script', 'micron-parser_original.js')
    if os.path.exists(micron_path):
        print(f"✅ Found Micron parser: {micron_path}")
    else:
        print(f"⚠️ Micron parser not found: {micron_path}")
        print("   Fallback parser will be used")
    
    # Start announce monitoring
    browser.start_monitoring()
    
    print("\n🌐 Starting local web server on http://localhost:5000")
    print("📡 Listening for NomadNetwork announces...")
    print("🔍 Open your browser to http://localhost:5000")
    print("\nPress Ctrl+C to stop")
    
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n👋 NomadNet Browser shutting down...")
        browser.running = False
        print("✅ Shutdown complete")

if __name__ == "__main__":
    main()