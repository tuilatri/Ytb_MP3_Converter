from flask import Flask, request, jsonify, send_file, render_template
import requests
import os
import re
import subprocess
import tempfile
from datetime import datetime
import logging
from dotenv import load_dotenv

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
if not RAPIDAPI_KEY:
    logger.error("RAPIDAPI_KEY not found in .env file")
    raise EnvironmentError("RAPIDAPI_KEY environment variable not set")

# **IMPROVEMENT:** Save files to a local 'downloads' directory within the project.
# This is safer, more portable, and avoids permission issues.
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    logger.info(f"Created download directory at: {DOWNLOAD_DIR}")

def clean_filename(title):
    """Sanitize filename by removing invalid characters."""
    invalid_chars = r'<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, '')
    return title[:150]  # Limit filename length to be safe

def find_ffmpeg():
    """Find FFmpeg executable in system PATH or common locations."""
    ffmpeg_commands = ['ffmpeg', 'ffmpeg.exe']
    
    for cmd in ffmpeg_commands:
        try:
            # Use DEVNULL to hide command output unless there's an error
            subprocess.run([cmd, '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Found FFmpeg: {cmd}")
            return cmd
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    logger.error("FFmpeg not found in system PATH.")
    return None

FFMPEG_PATH = find_ffmpeg()

def convert_to_mp3(input_file, output_file):
    """Convert audio file to MP3 format using FFmpeg."""
    if not FFMPEG_PATH:
        logger.error("FFmpeg executable not found, cannot convert.")
        return False
        
    try:
        cmd = [
            FFMPEG_PATH,
            '-i', input_file,
            '-codec:a', 'libmp3lame',
            '-b:a', '192k',
            '-y',
            output_file
        ]
        
        logger.info(f"Starting FFmpeg conversion for {os.path.basename(input_file)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            logger.info(f"FFmpeg conversion completed successfully for {os.path.basename(output_file)}")
            return True
        else:
            logger.error(f"FFmpeg conversion failed. Return code: {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg conversion timed out (5 minutes)")
        return False
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        return False

@app.route('/')
def index():
    # Use render_template to serve HTML from the 'templates' folder.
    # Make sure your index.html is inside a folder named 'templates'.
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    if not FFMPEG_PATH:
        return jsonify({'error': 'Server configuration error: FFmpeg not found.'}), 500

    data = request.get_json()
    youtube_url = data.get('url')
    if not youtube_url:
        return jsonify({'error': 'No URL provided'}), 400

    video_id_match = re.search(r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})', youtube_url)
    if not video_id_match:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    video_id = video_id_match.group(1)

    # Step 1: Fetch video details
    api_url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
    params = {'videoId': video_id}
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': 'youtube-media-downloader.p.rapidapi.com'
    }

    temp_file_path = None
    try:
        logger.info(f"Fetching details for video ID: {video_id}")
        response = requests.get(api_url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        api_data = response.json()

        if not isinstance(api_data, dict) or 'audios' not in api_data:
            logger.error(f"Invalid API response structure: {api_data}")
            return jsonify({'error': 'Could not retrieve video information.'}), 500

        title = clean_filename(api_data.get('title', 'audio'))
        audios = api_data.get('audios', {}).get('items', [])
        
        if not audios:
            logger.error(f"No audio formats available for video ID: {video_id}")
            return jsonify({'error': 'No audio formats found for this video.'}), 404

        # Select best audio: prefer m4a, otherwise largest file
        selected_audio = next((a for a in audios if 'audio/mp4' in a.get('mimeType','')), None)
        if not selected_audio:
            selected_audio = max(audios, key=lambda x: x.get('size', 0))

        download_url = selected_audio.get('url')
        if not download_url:
            logger.error("No download URL in selected audio format.")
            return jsonify({'error': 'Failed to get audio download link.'}), 500

        # Step 2: Download the audio to a temporary file
        original_extension = selected_audio.get('extension', 'tmp')
        with tempfile.NamedTemporaryFile(suffix=f'.{original_extension}', delete=False) as tf:
            temp_file_path = tf.name
        
        logger.info(f"Downloading audio to temp file: {temp_file_path}")
        audio_response = requests.get(download_url, stream=True, timeout=60)
        audio_response.raise_for_status()
        with open(temp_file_path, 'wb') as f:
            for chunk in audio_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        if os.path.getsize(temp_file_path) == 0:
            raise ValueError("Downloaded audio file is empty.")

        # Step 3: Convert to MP3
        mp3_filename = f"{title}.mp3"
        mp3_file_path = os.path.join(DOWNLOAD_DIR, mp3_filename)
        
        if not convert_to_mp3(temp_file_path, mp3_file_path):
            return jsonify({'error': 'Failed to convert audio to MP3.'}), 500

        logger.info(f"Successfully created MP3: {mp3_filename}")
        return jsonify({
            'download_url': f'/download/{mp3_filename}',
            'title': title
        })

    except requests.exceptions.RequestException as e:
        logger.error(f"API or download request error: {str(e)}")
        return jsonify({'error': f'Failed to fetch video data. Please try another video.'}), 500
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred.'}), 500
    finally:
        # Clean up the temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Cleaned up temp file: {temp_file_path}")
            except OSError as e:
                logger.warning(f"Failed to clean up temp file {temp_file_path}: {e}")

@app.route('/download/<path:filename>')
def download(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(file_path):
        logger.info(f"Serving file for download: {filename}")
        # **IMPROVEMENT:** Use `download_name` to provide a clean filename to the browser.
        return send_file(file_path, as_attachment=True, download_name=filename)
    else:
        logger.error(f"Download requested for non-existent file: {filename}")
        return jsonify({'error': 'File not found or has been cleaned up.'}), 404

@app.route('/cleanup')
def cleanup():
    """Remove files older than 1 hour from the local downloads folder."""
    now = datetime.now().timestamp()
    cleaned_files = 0
    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                file_age_seconds = now - os.path.getmtime(file_path)
                if file_age_seconds > 3600:  # 1 hour
                    os.remove(file_path)
                    logger.info(f"Cleaned up old file: {filename}")
                    cleaned_files += 1
        return jsonify({'status': f'Cleanup complete. Removed {cleaned_files} files.'})
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return jsonify({'error': 'Cleanup failed.'}), 500

if __name__ == '__main__':
    # Make sure to run with debug=False in a production environment
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)