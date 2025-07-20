from flask import Flask, request, jsonify, send_file
import requests
import os
import re
from datetime import datetime
import logging
from dotenv import load_dotenv

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
if not RAPIDAPI_KEY:
    logger.error("RAPIDAPI_KEY not found in .env file")
    raise EnvironmentError("RAPIDAPI_KEY environment variable not set")

# Get user's Downloads directory
pc_username = os.getenv('username') or os.getenv('USER')
if not pc_username:
    logger.error("Could not determine username for Downloads path")
    raise EnvironmentError("Environment variable 'username' or 'USER' not found")
DOWNLOAD_DIR = f'C:\\Users\\{pc_username}\\Downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def clean_filename(title):
    """Sanitize filename by removing invalid characters."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, '')
    return title[:100]  # Limit filename length

@app.route('/')
def index():
    return send_file('templates/index.html')

@app.route('/convert', methods=['POST'])
def convert():
    try:
        data = request.get_json()
        youtube_url = data.get('url')
        if not youtube_url:
            return jsonify({'error': 'No URL provided'}), 400

        # Extract video ID
        video_id_match = re.search(r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})', youtube_url)
        if not video_id_match:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        video_id = video_id_match.group(1)

        # Step 1: Fetch video details using youtube-media-downloader API
        api_url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
        params = {
            'videoId': video_id,
            'urlAccess': 'normal',
            'videos': 'auto',
            'audios': 'auto'
        }
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': 'youtube-media-downloader.p.rapidapi.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
        }

        logger.info(f"Making API request for video ID: {video_id}")
        response = requests.get(api_url, params=params, headers=headers)
        
        # Log the response status and content for debugging
        logger.info(f"API Response Status: {response.status_code}")
        logger.info(f"API Response Headers: {dict(response.headers)}")
        logger.info(f"API Response Content (first 500 chars): {response.text[:500]}")
        
        response.raise_for_status()
        
        # Check if the response is actually JSON
        try:
            api_data = response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response content: {response.text}")
            return jsonify({'error': 'Invalid response from video service. Please try again later.'}), 500

        # Validate that we got a dictionary response
        if not isinstance(api_data, dict):
            logger.error(f"Expected dict response, got {type(api_data)}: {api_data}")
            return jsonify({'error': 'Invalid response format from video service. Please try again later.'}), 500

        # Check if the API returned an error
        if 'error' in api_data:
            logger.error(f"API returned error: {api_data['error']}")
            return jsonify({'error': f"Video service error: {api_data['error']}"}), 400

        # Extract title and audio formats
        title = clean_filename(api_data.get('title', 'audio'))
        audios = api_data.get('audios', {})
        
        logger.info(f"Video title: {title}")
        logger.info(f"Audios data type: {type(audios)}")
        
        # Extract audio items from the nested structure
        audio_list = []
        if isinstance(audios, dict) and 'items' in audios:
            audio_list = audios['items']
        elif isinstance(audios, list):
            audio_list = audios
        elif isinstance(audios, dict):
            audio_list = list(audios.values())
        
        logger.info(f"Available audio formats: {len(audio_list)}")
        
        if not audio_list:
            logger.error(f"No audio formats available for video ID: {video_id}")
            return jsonify({'error': 'No audio formats available for this video. Try another video.'}), 400

        # Select the best audio format
        selected_audio = None
        
        # Look for MP4 audio (m4a) which is typically the highest quality
        for audio in audio_list:
            if not isinstance(audio, dict):
                continue
            
            mime_type = audio.get('mimeType', '').lower()
            extension = audio.get('extension', '').lower()
            
            logger.info(f"Audio format: {mime_type}, extension: {extension}, size: {audio.get('sizeText', 'unknown')}")
            
            # Prefer MP4 audio (m4a) as it's typically highest quality
            if 'audio/mp4' in mime_type or extension == 'm4a':
                selected_audio = audio
                break

        # If no MP4 found, select the largest audio file (usually highest quality)
        if not selected_audio and audio_list:
            # Sort by file size (descending) to get the highest quality
            audio_list_sorted = sorted(audio_list, key=lambda x: x.get('size', 0) if isinstance(x, dict) else 0, reverse=True)
            selected_audio = audio_list_sorted[0]
            logger.info("No MP4 found, using largest available audio format")

        if not selected_audio:
            logger.error(f"No suitable audio formats found for video ID: {video_id}")
            return jsonify({'error': 'No suitable audio formats available for this video. Try another video.'}), 400

        download_url = selected_audio.get('url')
        if not download_url:
            logger.error(f"No download URL found for selected audio format: {selected_audio}")
            return jsonify({'error': 'Failed to fetch audio download link'}), 500

        # Log selected audio format
        logger.info(f"Selected audio format: {selected_audio.get('mimeType')} ({selected_audio.get('extension')}) - {selected_audio.get('sizeText')}")

        # Step 2: Download and save the audio file
        # Determine the correct file extension
        extension = selected_audio.get('extension', 'mp3')
        if extension == 'm4a':
            # M4A is essentially MP4 audio, we can rename it to mp3 for compatibility
            # or keep as m4a - let's keep the original extension for now
            filename = f"{title}.{extension}"
        else:
            filename = f"{title}.mp3"
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        
        logger.info(f"Starting download of audio file: {filename}")
        audio_response = requests.get(download_url, stream=True)
        audio_response.raise_for_status()

        with open(file_path, 'wb') as f:
            for chunk in audio_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Verify file exists and is not empty
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found at {file_path}")
            return jsonify({'error': 'Failed to generate audio file'}), 500
        if os.path.getsize(file_path) == 0:
            logger.error(f"Generated audio file is empty: {file_path}")
            os.remove(file_path)
            return jsonify({'error': 'Generated audio file is empty'}), 500

        logger.info(f"Successfully downloaded: {filename} ({os.path.getsize(file_path)} bytes)")
        return jsonify({
            'download_url': f'/download/{filename}',
            'title': title
        })

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({'error': f'Failed to download video: {str(e)}. Try another video or check your connection.'}), 500
    except Exception as e:
        logger.error(f"Unexpected error during conversion: {str(e)}")
        logger.exception("Full traceback:")  # This will log the full stack trace
        return jsonify({'error': 'An unexpected error occurred during conversion.'}), 500

@app.route('/download/<filename>')
def download(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        logger.error(f"Download requested for non-existent file: {file_path}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/cleanup')
def cleanup():
    """Remove files older than 1 hour."""
    now = datetime.now()
    cleaned_files = 0
    for filename in os.listdir(DOWNLOAD_DIR):
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.isfile(file_path):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (now - file_mtime).total_seconds() > 3600:
                os.remove(file_path)
                logger.info(f"Deleted old file: {filename}")
                cleaned_files += 1
    return jsonify({'status': f'Cleanup completed. Removed {cleaned_files} files.'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)