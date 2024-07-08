#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import copy
import ipaddress
import json
import sys
from typing import cast, Dict
import unittest
from pytest_httpserver import HeaderValueMatcher
import pytest_httpserver
import pytest

sys.path.append("..")
import geoip2
from geoip2.errors import (
    AddressNotFoundError,
    AuthenticationError,
    GeoIP2Error,
    HTTPError,
    InvalidRequestError,
    OutOfQueriesError,
    PermissionRequiredError,
)
from geoip2.webservice import AsyncClient, Client


class TestBaseClient(unittest.TestCase):
    country = {
        "continent": {"code": "NA", "geoname_id": 42, "names": {"en": "North America"}},
        "country": {
            "geoname_id": 1,
            "iso_code": "US",
            "names": {"en": "United States of America"},
        },
        "maxmind": {"queries_remaining": 11},
        "registered_country": {
            "geoname_id": 2,
            "is_in_european_union": True,
            "iso_code": "DE",
            "names": {"en": "Germany"},
        },
        "traits": {
            "ip_address": "1.2.3.4",
            "is_anycast": True,
            "network": "1.2.3.0/24",
        },
    }

    # this is not a comprehensive representation of the
    # JSON from the server
    insights = cast(Dict, copy.deepcopy(country))
    insights["traits"]["user_count"] = 2
    insights["traits"]["static_ip_score"] = 1.3

    def _content_type(self, endpoint):
        return (
            "application/vnd.maxmind.com-"
            + endpoint
            + "+json; charset=UTF-8; version=1.0"
        )

    @pytest.fixture(autouse=True)
    def setup_httpserver(self, httpserver: pytest_httpserver.HTTPServer):
        self.httpserver = httpserver

    def test_country_ok(self):
        self.httpserver.expect_request("/geoip/v2.1/country/1.2.3.4").respond_with_json(
            self.country,
            status=200,
            content_type=self._content_type("country"),
        )
        country = self.run_client(self.client.country("1.2.3.4"))
        self.assertEqual(
            type(country), geoip2.models.Country, "return value of client.country"
        )
        self.assertEqual(country.continent.geoname_id, 42, "continent geoname_id is 42")
        self.assertEqual(country.continent.code, "NA", "continent code is NA")
        self.assertEqual(
            country.continent.name, "North America", "continent name is North America"
        )
        self.assertEqual(country.country.geoname_id, 1, "country geoname_id is 1")
        self.assertIs(
            country.country.is_in_european_union,
            False,
            "country is_in_european_union is False",
        )
        self.assertEqual(country.country.iso_code, "US", "country iso_code is US")
        self.assertEqual(
            country.country.names, {"en": "United States of America"}, "country names"
        )
        self.assertEqual(
            country.country.name,
            "United States of America",
            "country name is United States of America",
        )
        self.assertEqual(
            country.maxmind.queries_remaining, 11, "queries_remaining is 11"
        )
        self.assertIs(
            country.registered_country.is_in_european_union,
            True,
            "registered_country is_in_european_union is True",
        )
        self.assertEqual(
            country.traits.network, ipaddress.ip_network("1.2.3.0/24"), "network"
        )
        self.assertTrue(country.traits.is_anycast)
        self.assertEqual(country.raw, self.country, "raw response is correct")

    def test_me(self):
        self.httpserver.expect_request("/geoip/v2.1/country/me").respond_with_json(
            self.country,
            status=200,
            content_type=self._content_type("country"),
        )
        implicit_me = self.run_client(self.client.country())
        self.assertEqual(
            type(implicit_me), geoip2.models.Country, "country() returns Country object"
        )
        explicit_me = self.run_client(self.client.country())
        self.assertEqual(
            type(explicit_me),
            geoip2.models.Country,
            "country('me') returns Country object",
        )

    def test_200_error(self):
        self.httpserver.expect_request("/geoip/v2.1/country/1.1.1.1").respond_with_data(
            "",
            status=200,
            content_type=self._content_type("country"),
        )

        with self.assertRaisesRegex(
            GeoIP2Error, "could not decode the response as JSON"
        ):
            self.run_client(self.client.country("1.1.1.1"))

    def test_bad_ip_address(self):
        with self.assertRaisesRegex(
            ValueError, "'1.2.3' does not appear to be an IPv4 " "or IPv6 address"
        ):
            self.run_client(self.client.country("1.2.3"))

    def test_no_body_error(self):
        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.7"
        ).respond_with_data(
            "",
            status=400,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(
            HTTPError, "Received a 400 error for .* with no body"
        ):
            self.run_client(self.client.country("1.2.3.7"))

    def test_weird_body_error(self):

        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.8"
        ).respond_with_json(
            {"wierd": 42},
            status=400,
            content_type=self._content_type("country"),
        )

        with self.assertRaisesRegex(
            HTTPError,
            "Response contains JSON but it does not " "specify code or error keys",
        ):
            self.run_client(self.client.country("1.2.3.8"))

    def test_bad_body_error(self):

        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.9"
        ).respond_with_data(
            "bad body",
            status=400,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(
            HTTPError, "it did not include the expected JSON body"
        ):
            self.run_client(self.client.country("1.2.3.9"))

    def test_500_error(self):
        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.10"
        ).respond_with_data(
            "",
            status=500,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(HTTPError, r"Received a server error \(500\) for"):
            self.run_client(self.client.country("1.2.3.10"))

    def test_300_error(self):

        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.11"
        ).respond_with_data(
            "",
            status=300,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(
            HTTPError, r"Received a very surprising HTTP status \(300\) for"
        ):
            self.run_client(self.client.country("1.2.3.11"))

    def test_ip_address_required(self):
        self._test_error(400, "IP_ADDRESS_REQUIRED", InvalidRequestError)

    def test_ip_address_not_found(self):
        self._test_error(404, "IP_ADDRESS_NOT_FOUND", AddressNotFoundError)

    def test_ip_address_reserved(self):
        self._test_error(400, "IP_ADDRESS_RESERVED", AddressNotFoundError)

    def test_permission_required(self):
        self._test_error(403, "PERMISSION_REQUIRED", PermissionRequiredError)

    def test_auth_invalid(self):
        self._test_error(400, "AUTHORIZATION_INVALID", AuthenticationError)

    def test_license_key_required(self):
        self._test_error(401, "LICENSE_KEY_REQUIRED", AuthenticationError)

    def test_account_id_required(self):
        self._test_error(401, "ACCOUNT_ID_REQUIRED", AuthenticationError)

    def test_user_id_required(self):
        self._test_error(401, "USER_ID_REQUIRED", AuthenticationError)

    def test_account_id_unkown(self):
        self._test_error(401, "ACCOUNT_ID_UNKNOWN", AuthenticationError)

    def test_user_id_unkown(self):
        self._test_error(401, "USER_ID_UNKNOWN", AuthenticationError)

    def test_out_of_queries_error(self):
        self._test_error(402, "OUT_OF_QUERIES", OutOfQueriesError)

    def _test_error(self, status, error_code, error_class):
        msg = "Some error message"
        body = {"error": msg, "code": error_code}
        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.18"
        ).respond_with_json(
            body,
            status=status,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(error_class, msg):
            self.run_client(self.client.country("1.2.3.18"))

    def test_unknown_error(self):
        msg = "Unknown error type"
        ip = "1.2.3.19"
        body = {"error": msg, "code": "UNKNOWN_TYPE"}
        self.httpserver.expect_request("/geoip/v2.1/country/" + ip).respond_with_json(
            body,
            status=400,
            content_type=self._content_type("country"),
        )
        with self.assertRaisesRegex(InvalidRequestError, msg):
            self.run_client(self.client.country(ip))

    def test_request(self):
        matcher = HeaderValueMatcher({
            "Accept": "application/json",
            "Authorization":"Basic NDI6YWJjZGVmMTIzNDU2",                
            "User-Agent": lambda x: x.startswith("GeoIP2-Python-Client/"),})
        self.httpserver.expect_request(
            "/geoip/v2.1/country/1.2.3.4",
            header_value_matcher=matcher,
            
        ).respond_with_json(
            self.country,
            status=200,
            content_type=self._content_type("country"),
        )
        self.run_client(self.client.country("1.2.3.4"))

    def test_city_ok(self):
        self.httpserver.expect_request("/geoip/v2.1/city/1.2.3.4").respond_with_json(
            self.country,
            status=200,
            content_type=self._content_type("city"),
        )
        city = self.run_client(self.client.city("1.2.3.4"))
        self.assertEqual(type(city), geoip2.models.City, "return value of client.city")
        self.assertEqual(
            city.traits.network, ipaddress.ip_network("1.2.3.0/24"), "network"
        )
        self.assertTrue(city.traits.is_anycast)

    def test_insights_ok(self):
        self.httpserver.expect_request(
            "/geoip/v2.1/insights/1.2.3.4"
        ).respond_with_json(
            self.insights,
            status=200,
            content_type=self._content_type("insights"),
        )
        insights = self.run_client(self.client.insights("1.2.3.4"))
        self.assertEqual(
            type(insights), geoip2.models.Insights, "return value of client.insights"
        )
        self.assertEqual(
            insights.traits.network, ipaddress.ip_network("1.2.3.0/24"), "network"
        )
        self.assertTrue(insights.traits.is_anycast)
        self.assertEqual(insights.traits.static_ip_score, 1.3, "static_ip_score is 1.3")
        self.assertEqual(insights.traits.user_count, 2, "user_count is 2")

    def test_named_constructor_args(self):
        id = 47
        key = "1234567890ab"
        client = self.client_class(account_id=id, license_key=key)
        self.assertEqual(client._account_id, str(id))
        self.assertEqual(client._license_key, key)

    def test_missing_constructor_args(self):
        with self.assertRaises(TypeError):
            self.client_class(license_key="1234567890ab")

        with self.assertRaises(TypeError):
            self.client_class("47")


class TestClient(TestBaseClient):
    def setUp(self):
        self.client_class = Client
        self.client = Client(42, "abcdef123456")
        self.client._base_uri = self.httpserver.url_for("/geoip/v2.1")

    def run_client(self, v):
        return v


class TestAsyncClient(TestBaseClient):
    def setUp(self):
        self._loop = asyncio.new_event_loop()
        self.client_class = AsyncClient
        self.client = AsyncClient(42, "abcdef123456")
        self.client._base_uri = self.httpserver.url_for("/geoip/v2.1")

    def tearDown(self):
        self._loop.run_until_complete(self.client.close())
        self._loop.close()

    def run_client(self, v):
        return self._loop.run_until_complete(v)


del TestBaseClient


if __name__ == "__main__":
    unittest.main()
