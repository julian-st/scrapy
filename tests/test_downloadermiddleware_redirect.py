import unittest
from itertools import chain, product

import pytest

from scrapy.downloadermiddlewares.redirect import (
    MetaRefreshMiddleware,
    RedirectMiddleware,
)
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Request, Response
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class RedirectMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")
        self.mw = RedirectMiddleware.from_crawler(self.crawler)

    def test_priority_adjust(self):
        req = Request("http://a.com")
        rsp = Response(
            "http://a.com", headers={"Location": "http://a.com/redirected"}, status=301
        )
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority > req.priority

    def test_redirect_3xx_permanent(self):
        def _test(method, status=301):
            url = f"http://www.example.com/{status}"
            url2 = "http://www.example.com/redirected"
            req = Request(url, method=method)
            rsp = Response(url, headers={"Location": url2}, status=status)

            req2 = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req2, Request)
            self.assertEqual(req2.url, url2)
            self.assertEqual(req2.method, method)

            # response without Location header but with status code is 3XX should be ignored
            del rsp.headers["Location"]
            assert self.mw.process_response(req, rsp, self.spider) is rsp

        _test("GET")
        _test("POST")
        _test("HEAD")

        _test("GET", status=307)
        _test("POST", status=307)
        _test("HEAD", status=307)

        _test("GET", status=308)
        _test("POST", status=308)
        _test("HEAD", status=308)

    def test_dont_redirect(self):
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"
        req = Request(url, meta={"dont_redirect": True})
        rsp = Response(url, headers={"Location": url2}, status=301)

        r = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(r, Response)
        assert r is rsp

        # Test that it redirects when dont_redirect is False
        req = Request(url, meta={"dont_redirect": False})
        rsp = Response(url2, status=200)

        r = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(r, Response)
        assert r is rsp

    def test_redirect_302(self):
        url = "http://www.example.com/302"
        url2 = "http://www.example.com/redirected2"
        req = Request(
            url,
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, "GET")
        assert (
            "Content-Type" not in req2.headers
        ), "Content-Type header must not be present in redirected request"
        assert (
            "Content-Length" not in req2.headers
        ), "Content-Length header must not be present in redirected request"
        assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers["Location"]
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_redirect_302_head(self):
        url = "http://www.example.com/302"
        url2 = "http://www.example.com/redirected2"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, "HEAD")

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers["Location"]
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_redirect_302_relative(self):
        url = "http://www.example.com/302"
        url2 = "///i8n.example2.com/302"
        url3 = "http://i8n.example2.com/302"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url3)
        self.assertEqual(req2.method, "HEAD")

        # response without Location header but with status code is 3XX should be ignored
        del rsp.headers["Location"]
        assert self.mw.process_response(req, rsp, self.spider) is rsp

    def test_max_redirect_times(self):
        self.mw.max_redirect_times = 1
        req = Request("http://scrapytest.org/302")
        rsp = Response(
            "http://scrapytest.org/302", headers={"Location": "/redirected"}, status=302
        )

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        assert "redirect_times" in req.meta
        self.assertEqual(req.meta["redirect_times"], 1)
        self.assertRaises(
            IgnoreRequest, self.mw.process_response, req, rsp, self.spider
        )

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request("http://scrapytest.org/302", meta={"redirect_ttl": 1})
        rsp = Response(
            "http://www.scrapytest.org/302",
            headers={"Location": "/redirected"},
            status=302,
        )

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertRaises(
            IgnoreRequest, self.mw.process_response, req, rsp, self.spider
        )

    def test_redirect_urls(self):
        req1 = Request("http://scrapytest.org/first")
        rsp1 = Response(
            "http://scrapytest.org/first",
            headers={"Location": "/redirected"},
            status=302,
        )
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        rsp2 = Response(
            "http://scrapytest.org/redirected",
            headers={"Location": "/redirected2"},
            status=302,
        )
        req3 = self.mw.process_response(req2, rsp2, self.spider)

        self.assertEqual(req2.url, "http://scrapytest.org/redirected")
        self.assertEqual(req2.meta["redirect_urls"], ["http://scrapytest.org/first"])
        self.assertEqual(req3.url, "http://scrapytest.org/redirected2")
        self.assertEqual(
            req3.meta["redirect_urls"],
            ["http://scrapytest.org/first", "http://scrapytest.org/redirected"],
        )

    def test_redirect_reasons(self):
        req1 = Request("http://scrapytest.org/first")
        rsp1 = Response(
            "http://scrapytest.org/first",
            headers={"Location": "/redirected1"},
            status=301,
        )
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        rsp2 = Response(
            "http://scrapytest.org/redirected1",
            headers={"Location": "/redirected2"},
            status=301,
        )
        req3 = self.mw.process_response(req2, rsp2, self.spider)

        self.assertEqual(req2.meta["redirect_reasons"], [301])
        self.assertEqual(req3.meta["redirect_reasons"], [301, 301])

    def test_spider_handling(self):
        smartspider = self.crawler._create_spider("smarty")
        smartspider.handle_httpstatus_list = [404, 301, 302]
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"
        req = Request(url)
        rsp = Response(url, headers={"Location": url2}, status=301)
        r = self.mw.process_response(req, rsp, smartspider)
        self.assertIs(r, rsp)

    def test_request_meta_handling(self):
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"

        def _test_passthrough(req):
            rsp = Response(url, headers={"Location": url2}, status=301, request=req)
            r = self.mw.process_response(req, rsp, self.spider)
            self.assertIs(r, rsp)

        _test_passthrough(
            Request(url, meta={"handle_httpstatus_list": [404, 301, 302]})
        )
        _test_passthrough(Request(url, meta={"handle_httpstatus_all": True}))

    def test_latin1_location(self):
        req = Request("http://scrapytest.org/first")
        latin1_location = "/ação".encode("latin1")  # HTTP historically supports latin1
        resp = Response(
            "http://scrapytest.org/first",
            headers={"Location": latin1_location},
            status=302,
        )
        req_result = self.mw.process_response(req, resp, self.spider)
        perc_encoded_utf8_url = "http://scrapytest.org/a%E7%E3o"
        self.assertEqual(perc_encoded_utf8_url, req_result.url)

    def test_utf8_location(self):
        req = Request("http://scrapytest.org/first")
        utf8_location = "/ação".encode("utf-8")  # header using UTF-8 encoding
        resp = Response(
            "http://scrapytest.org/first",
            headers={"Location": utf8_location},
            status=302,
        )
        req_result = self.mw.process_response(req, resp, self.spider)
        perc_encoded_utf8_url = "http://scrapytest.org/a%C3%A7%C3%A3o"
        self.assertEqual(perc_encoded_utf8_url, req_result.url)

    def test_cross_domain_header_dropping(self):
        safe_headers = {"A": "B"}
        original_request = Request(
            "https://example.com",
            headers={"Cookie": "a=b", "Authorization": "a", **safe_headers},
        )

        internal_response = Response(
            "https://example.com",
            headers={"Location": "https://example.com/a"},
            status=301,
        )
        internal_redirect_request = self.mw.process_response(
            original_request, internal_response, self.spider
        )
        self.assertIsInstance(internal_redirect_request, Request)
        self.assertEqual(original_request.headers, internal_redirect_request.headers)

        external_response = Response(
            "https://example.com",
            headers={"Location": "https://example.org/a"},
            status=301,
        )
        external_redirect_request = self.mw.process_response(
            original_request, external_response, self.spider
        )
        self.assertIsInstance(external_redirect_request, Request)
        self.assertEqual(
            safe_headers, external_redirect_request.headers.to_unicode_dict()
        )


SCHEME_PARAMS = ("url", "location", "target")
HTTP_SCHEMES = ("http", "https")
NON_HTTP_SCHEMES = ("data", "file", "ftp", "s3", "foo")
REDIRECT_SCHEME_CASES = (
    # http/https → http/https redirects
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            f"{output_scheme}://example.com/b",
        )
        for input_scheme, output_scheme in product(HTTP_SCHEMES, repeat=2)
    ),
    # http/https → data/file/ftp/s3/foo does not redirect
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            None,
        )
        for input_scheme in HTTP_SCHEMES
        for output_scheme in NON_HTTP_SCHEMES
    ),
    # http/https → relative redirects
    *(
        (
            f"{scheme}://example.com/a",
            location,
            f"{scheme}://example.com/b",
        )
        for scheme in HTTP_SCHEMES
        for location in ("//example.com/b", "/b")
    ),
    # Note: We do not test data/file/ftp/s3 schemes for the initial URL
    # because their download handlers cannot return a status code of 3xx.
)


@pytest.mark.parametrize(SCHEME_PARAMS, REDIRECT_SCHEME_CASES)
def test_redirect_schemes(url, location, target):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider("foo")
    mw = RedirectMiddleware.from_crawler(crawler)
    request = Request(url)
    response = Response(url, headers={"Location": location}, status=301)
    redirect = mw.process_response(request, response, spider)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)
        assert redirect.url == target


def meta_refresh_body(url, interval=5):
    html = f"""<html><head><meta http-equiv="refresh" content="{interval};url={url}"/></head></html>"""
    return html.encode("utf-8")


class MetaRefreshMiddlewareTest(unittest.TestCase):
    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider("foo")
        self.mw = MetaRefreshMiddleware.from_crawler(crawler)

    def _body(self, interval=5, url="http://example.org/newpage"):
        return meta_refresh_body(url, interval)

    def test_priority_adjust(self):
        req = Request("http://a.com")
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert req2.priority > req.priority

    def test_meta_refresh(self):
        req = Request(url="http://example.org")
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, "http://example.org/newpage")

    def test_meta_refresh_with_high_interval(self):
        # meta-refresh with high intervals don't trigger redirects
        req = Request(url="http://example.org")
        rsp = HtmlResponse(
            url="http://example.org", body=self._body(interval=1000), encoding="utf-8"
        )
        rsp2 = self.mw.process_response(req, rsp, self.spider)
        assert rsp is rsp2

    def test_meta_refresh_trough_posted_request(self):
        req = Request(
            url="http://example.org",
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)

        assert isinstance(req2, Request)
        self.assertEqual(req2.url, "http://example.org/newpage")
        self.assertEqual(req2.method, "GET")
        assert (
            "Content-Type" not in req2.headers
        ), "Content-Type header must not be present in redirected request"
        assert (
            "Content-Length" not in req2.headers
        ), "Content-Length header must not be present in redirected request"
        assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

    def test_max_redirect_times(self):
        self.mw.max_redirect_times = 1
        req = Request("http://scrapytest.org/max")
        rsp = HtmlResponse(req.url, body=self._body())

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        assert "redirect_times" in req.meta
        self.assertEqual(req.meta["redirect_times"], 1)
        self.assertRaises(
            IgnoreRequest, self.mw.process_response, req, rsp, self.spider
        )

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request("http://scrapytest.org/302", meta={"redirect_ttl": 1})
        rsp = HtmlResponse(req.url, body=self._body())

        req = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req, Request)
        self.assertRaises(
            IgnoreRequest, self.mw.process_response, req, rsp, self.spider
        )

    def test_redirect_urls(self):
        req1 = Request("http://scrapytest.org/first")
        rsp1 = HtmlResponse(req1.url, body=self._body(url="/redirected"))
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        assert isinstance(req2, Request), req2
        rsp2 = HtmlResponse(req2.url, body=self._body(url="/redirected2"))
        req3 = self.mw.process_response(req2, rsp2, self.spider)
        assert isinstance(req3, Request), req3
        self.assertEqual(req2.url, "http://scrapytest.org/redirected")
        self.assertEqual(req2.meta["redirect_urls"], ["http://scrapytest.org/first"])
        self.assertEqual(req3.url, "http://scrapytest.org/redirected2")
        self.assertEqual(
            req3.meta["redirect_urls"],
            ["http://scrapytest.org/first", "http://scrapytest.org/redirected"],
        )

    def test_redirect_reasons(self):
        req1 = Request("http://scrapytest.org/first")
        rsp1 = HtmlResponse(
            "http://scrapytest.org/first", body=self._body(url="/redirected")
        )
        req2 = self.mw.process_response(req1, rsp1, self.spider)
        rsp2 = HtmlResponse(
            "http://scrapytest.org/redirected", body=self._body(url="/redirected1")
        )
        req3 = self.mw.process_response(req2, rsp2, self.spider)

        self.assertEqual(req2.meta["redirect_reasons"], ["meta refresh"])
        self.assertEqual(
            req3.meta["redirect_reasons"], ["meta refresh", "meta refresh"]
        )

    def test_ignore_tags_default(self):
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, "http://example.org/newpage")

    def test_ignore_tags_1_x_list(self):
        """Test that Scrapy 1.x behavior remains possible"""
        settings = {"METAREFRESH_IGNORE_TAGS": ["script", "noscript"]}
        crawler = get_crawler(Spider, settings)
        mw = MetaRefreshMiddleware.from_crawler(crawler)
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        response = mw.process_response(req, rsp, self.spider)
        assert isinstance(response, Response)


@pytest.mark.parametrize(
    SCHEME_PARAMS,
    (
        *REDIRECT_SCHEME_CASES,
        # data/file/ftp/s3/foo → * does not redirect
        *(
            (
                f"{input_scheme}://example.com/a",
                f"{output_scheme}://example.com/b",
                None,
            )
            for input_scheme in NON_HTTP_SCHEMES
            for output_scheme in chain(HTTP_SCHEMES, NON_HTTP_SCHEMES)
        ),
        # data/file/ftp/s3/foo → relative does not redirect
        *(
            (
                f"{scheme}://example.com/a",
                location,
                None,
            )
            for scheme in NON_HTTP_SCHEMES
            for location in ("//example.com/b", "/b")
        ),
    ),
)
def test_meta_refresh_schemes(url, location, target):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider("foo")
    mw = MetaRefreshMiddleware.from_crawler(crawler)
    request = Request(url)
    response = HtmlResponse(url, body=meta_refresh_body(location))
    redirect = mw.process_response(request, response, spider)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)
        assert redirect.url == target


if __name__ == "__main__":
    unittest.main()
