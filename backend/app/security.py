from django.utils.cache import patch_vary_headers


PRIVATE_NO_STORE = "private, no-store, no-cache, must-revalidate, max-age=0"


class NoStoreApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/0x/"):
            response["Cache-Control"] = PRIVATE_NO_STORE
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response["CDN-Cache-Control"] = PRIVATE_NO_STORE
            response["Cloudflare-CDN-Cache-Control"] = PRIVATE_NO_STORE
            patch_vary_headers(response, ("Authorization", "Cookie"))
        return response
