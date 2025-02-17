from flask import Flask, render_template, request
from flask_uploads import UploadSet, configure_uploads, IMAGES
import requests

app = Flask(__name__)

photos = UploadSet('photos', IMAGES)

app.config['UPLOADED_PHOTOS_DEST'] = 'static/img'
configure_uploads(app, photos)

def ocr_space_file(filename, overlay=False, api_key='K81568317388957', language='eng'):  

    payload = {'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               }

    with open(filename, 'rb') as f:
        r = requests.post('https://api.ocr.space/parse/image',
                          files={filename: f},
                          data=payload,
                          )
    return r.content.decode()

@app.route('/', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST' and 'photo' in request.files:
        filename = photos.save(request.files['photo'])
        result = ocr_space_file('static/img/' + filename)

        return result

    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)