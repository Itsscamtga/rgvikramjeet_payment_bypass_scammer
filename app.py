from flask import Flask, request, jsonify
import requests
import base64
import json
import threading
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

app = Flask(__name__)
results = {}  # Stores results by request ID

# 🔹 Endpoint to start processing (Instant response)
@app.route('/get_layer_two_data', methods=['GET'])
def get_layer_two_data():
    try:
        tiles_input_data2 = request.args.get('tiles_input_data2', '').split('|')
        course_id = request.args.get('course_id', '')
        parent_id = request.args.get('parent_id', '')
        csrf_name = request.args.get('csrf_name', '')
        req_id = f"{course_id}_{parent_id}_{int(time.time())}"

        if not all([tiles_input_data2, course_id, parent_id, csrf_name]):
            return jsonify({'status': 'error', 'message': 'Missing required parameters'}), 400

        # Start background thread
        thread = threading.Thread(
            target=process_data,
            args=(req_id, tiles_input_data2, course_id, parent_id, csrf_name)
        )
        thread.start()

        return jsonify({
            'status': 'processing',
            'message': 'Processing started. Use /get_status?req_id=... to check progress.',
            'req_id': req_id
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 🔹 Endpoint to get status/result
@app.route('/get_status', methods=['GET'])
def get_status():
    req_id = request.args.get("req_id", "")
    if req_id in results:
        return jsonify({'status': 'done', 'data': results.pop(req_id)})
    return jsonify({'status': 'processing', 'message': 'Still working...'})

# 🔹 Background data processing function
def process_data(req_id, tiles_input_data2, course_id, parent_id, csrf_name):
    session = requests.Session()
    video_urls, pdf_urls = send_layer_two2_requests(
        tiles_input_data2=tiles_input_data2,
        course_id=course_id,
        parent_id=parent_id,
        csrf_name=csrf_name,
        session=session
    )
    results[req_id] = {
        'video_urls': video_urls,
        'pdf_urls': pdf_urls
    }

# 🔹 Base64 encoding without space
def simple_encode_without_spaces(data_dict):
    json_str = json.dumps(data_dict, separators=(',', ':'))
    encoded_bytes = base64.urlsafe_b64encode(json_str.encode('utf-8'))
    return encoded_bytes.decode('utf-8')

# 🔹 Base64 decode
def simple_decode(encoded_str):
    try:
        padded = encoded_str + '=' * (-len(encoded_str) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

# 🔹 Layer 2 data extraction
def send_layer_two2_requests(tiles_input_data2, course_id, parent_id, csrf_name, session):
    url = 'https://rgvikramjeet.videocrypt.in/web/Course/get_layer_two_data'

    cookies = {
        'csrf_name': csrf_name,
    }

    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://rgvikramjeet.videocrypt.in',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'X-Requested-With': 'XMLHttpRequest',
    }

    video_urls = []
    pdf_urls = []
    unique_entries = set()

    for item in tiles_input_data2:
        try:
            topic_id, tile_id, type_, subject_id = map(str.strip, item.split(":"))
            payload_dict = {
                "course_id": course_id,
                "parent_id": parent_id,
                "layer": 3,
                "page": 1,
                "revert_api": "1#0#0#0",
                "subject_id": subject_id,
                "tile_id": tile_id,
                "topic_id": topic_id,
                "type": type_,
            }

            payload_str = simple_encode_without_spaces(payload_dict)
            data = {
                'layer_two_input_data': payload_str,
                'content': 'content',
                'csrf_name': csrf_name
            }

            r = session.post(url, cookies=cookies, headers=headers, data=data)
            r.raise_for_status()
            json_data = simple_decode(r.json().get("response", ""))
            video_list = json_data.get("data", {}).get("list", [])

            for video in video_list:
                title = video.get("title", "").strip()
                file_url = video.get("file_url", "").strip()
                join_url = video.get("join_url", "").strip()
                vdc_id = video.get("vdc_id", "").strip()
                final_url = ""

                if vdc_id:
                    try:
                        auth_data = {
                            'token': vdc_id,
                            'device': 'Win32',
                            'browser': 'windowchrome',
                        }
                        auth_response = session.post(
                            'https://rgvikramjeet.videocrypt.in/web/Auth/video',
                            cookies=cookies, headers=headers, data=auth_data
                        )
                        auth_response.raise_for_status()
                        auth_json = auth_response.json()

                        if auth_json.get("status") is False:
                            raise ValueError("vdc_id returned status False")

                        auth_data_dict = auth_json.get("data", {})
                        raw_file_url = auth_data_dict.get("file_url", "").replace("\\", "")
                        if raw_file_url.endswith(".m3u8"):
                            final_url = raw_file_url
                        else:
                            for item in auth_data_dict.get("list", []):
                                jurl = item.get("join_url", "")
                                if jurl.endswith(".m3u8"):
                                    final_url = jurl
                                    break

                    except Exception as ve:
                        print(f"⚠️ vdc_id failed: {vdc_id} → Fallback to join_url/file_url")
                        if file_url.endswith(".m3u8"):
                            final_url = file_url
                        elif join_url.endswith(".m3u8") or join_url.endswith(".pdf"):
                            final_url = join_url

                else:
                    if file_url.endswith(".m3u8"):
                        final_url = file_url
                    elif join_url.endswith(".m3u8") or join_url.endswith(".pdf"):
                        final_url = join_url

                entry = f"{title} : {final_url}"
                if final_url.endswith(".m3u8"):
                    if entry not in unique_entries:
                        video_urls.append(entry)
                        unique_entries.add(entry)
                    else:
                        print(f"⚠️ Duplicate video skipped: {entry}")
                elif final_url.endswith(".pdf"):
                    if entry not in unique_entries:
                        pdf_urls.append(entry)
                        unique_entries.add(entry)
                    else:
                        print(f"⚠️ Duplicate PDF skipped: {entry}")
                else:
                    print(f"⚠️ No valid video/pdf URL found for: {title}")

        except Exception as e:
            print(f"❌ Error processing {item}: {e}")

    return video_urls, pdf_urls

# 🔹 Run app
if __name__ == '__main__':
    app.run(debug=True)
