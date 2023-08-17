import json

from io import BytesIO
from ntech import sfapi_client
from facerouter.plugin import Plugin
import tornado.httpclient
import mimetypes


def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def encode_multipart_formdata(fields, files, boundary=None):
    validated_boundary = boundary if boundary else '----------ThIs_Is_tHe_bouNdaRY_$'
    l = []
    for item in fields:
        key, value = item[0], item[1]
        l.append('--' + validated_boundary)
        l.append('Content-Disposition: form-data; name="%s"' % key)
        if len(item) > 2:
            l.append('Content-Type: {}'.format(item[2]))
        l.append('')
        if value is str:
            l.append(value)
        else:
            l.append(json.dumps(value).encode('utf8'))
    for file in files:
        key, filename, value = file
        l.append('--' + validated_boundary)
        l.append(
            'Content-Disposition: form-data; name="%s"; filename="%s"' % (
                key, filename
            )
        )
        l.append('Content-Type: %s' % get_content_type(filename))
        l.append('')
        l.append(bytearray(value))
    l.append('--' + validated_boundary + '--')
    l.append('')

    result = []
    for item in l:
        if type(item) is str:
            result.append(bytearray(item, 'utf8'))
        else:
            result.append(item)
    body = bytearray('\r\n', 'utf8').join(result)
    body = bytes(body)
    content_type = 'multipart/form-data; boundary=%s' % validated_boundary
    return content_type, body


class UnliftPlugin(Plugin):
    def __init__(self, ctx):
        super().__init__(ctx)

    async def preprocess(self, request, labels):
        return "facen", 

    async def process(self, request, photo, bbox, event_id, detection):
        photo_bytes = BytesIO(photo).getvalue()
        gallery = self.ctx.sfapi['default']
        detection_filter = sfapi_client.filters.Detection(detection.id, 0.1)
        print('detection filter: ' + str(detection_filter))
        res = await gallery.list(filters=[detection_filter], limit=1)

        identify_result = next(iter(res), None)
        if identify_result is not None:
            identify_result = {
                'id': identify_result.id.face,
                'gallery': identify_result.id.gallery,
                'features': identify_result.features,
                'meta': identify_result.meta,
                'confidence': identify_result.confidence
            }
        data = [("x1", bbox.left),
                ("y1", bbox.top),
                ("y2", bbox.bottom),
                ("x2", bbox.right),
                ("detectorParams", request.params.detectorParams),
                ("cam_id", request.params.cam_id),
                ("identify_result", identify_result),
                ("features", detection.features)]
        file = ('photo', 'photo.jpg', photo_bytes)

        content_type, body = encode_multipart_formdata(data, [file])
        tornado.httpclient.HTTPClient().fetch(
            tornado.httpclient.HTTPRequest(
                url='http://127.0.0.1:8888/v2/face',
                method="POST",
                body=body,
                headers={"Content-Type": content_type},
                follow_redirects=False,
                request_timeout=3))


def activate(app, ctx, plugin_name, plugin_source):
    print("app", app)
    print("ctx", ctx)
    print("plugin_name", plugin_name)
    print("plugin_source", plugin_source)
    return UnliftPlugin(ctx)
