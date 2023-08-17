import mimetypes
import tornado.httpclient


def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def encode_multipart_formdata(fields, files, boundary=None):
    """
    fields is a sequence of (name, value) elements for regular form fields.
    files is a sequence of (name, filename, value) elements for data to be
    uploaded as files.
    Return (content_type, body) ready for httplib.HTTP instance
    """

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
            l.append(str(value).encode('utf8'))
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


class FindFaceApiClient:
    def __init__(self, api_host, api_port, api_token):
        self.host = api_host
        self.port = api_port
        self.token = api_token

    def detect(self, frameImgArr):
        body, content_type = self.get_detect_data(frameImgArr)
        return tornado.httpclient.HTTPClient().fetch(
            tornado.httpclient.HTTPRequest(
                url="http://%s:%s%s" % (self.host, self.port, '/v1/detect'),
                method="POST",
                body=body,
                headers={"Authorization": "Token " + self.token, "Content-Type": content_type},
                follow_redirects=False,
                request_timeout=5))

    def detect_async(self, frameImgArr, callback):
        body, content_type = self.get_detect_data(frameImgArr)
        tornado.httpclient.AsyncHTTPClient().fetch(
            tornado.httpclient.HTTPRequest(
                url="http://%s:%s%s" % (self.host, self.port, '/v1/detect'),
                method="POST",
                body=body,
                headers={"Authorization": "Token " + self.token, "Content-Type": content_type},
                follow_redirects=False,
                request_timeout=5),
            callback=callback)

    @staticmethod
    def get_detect_data(frameImgArr):
        file = ('photo', 'image.jpg', frameImgArr)
        content_type, body = encode_multipart_formdata(
            [("age", True), ("emotions", True), ("gender", True)], [file])
        return body, content_type

    def verify(self, img1, img2):
        files = [('photo1', 'image.jpg', img1), ('photo2', 'image2.jpg', img2)]
        content_type, body = encode_multipart_formdata([("threshold", 0.78)], files)
        return tornado.httpclient.HTTPClient().fetch(
            tornado.httpclient.HTTPRequest(
                url="http://%s:%s%s" % (self.host, self.port, '/v0/verify'),
                method="POST",
                body=body,
                headers={"Authorization": "Token " + self.token, "Content-Type": content_type},
                follow_redirects=False))

    def identify_async(self, args, files, boundary, callback):
        content_type, body = encode_multipart_formdata(args, files, boundary)
        tornado.httpclient.AsyncHTTPClient().fetch(
            tornado.httpclient.HTTPRequest(
                url="http://%s:%s%s" % (self.host, self.port, '/v0/identify'),
                method="POST",
                body=body,
                headers={"Authorization": "Token " + self.token, "Content-Type": content_type},
                follow_redirects=False),
            callback=callback)
