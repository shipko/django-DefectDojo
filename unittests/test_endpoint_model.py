import datetime
from .dojo_test_case import DojoTestCase

from dojo.endpoint.utils import endpoint_get_or_create
from dojo.models import Product_Type, Product, Engagement, Test, Finding, Endpoint, Endpoint_Status
from django.core.exceptions import ValidationError
from django.apps import apps
from django.utils import timezone
from dojo.endpoint.utils import remove_broken_endpoint_statuses


class TestEndpointModel(DojoTestCase):

    def test_empty(self):
        endpoint = Endpoint()
        self.assertIsNone(endpoint.protocol)
        self.assertIsNone(endpoint.userinfo)
        self.assertIsNone(endpoint.host)
        self.assertIsNone(endpoint.port)
        self.assertIsNone(endpoint.path)
        self.assertIsNone(endpoint.query)
        self.assertIsNone(endpoint.fragment)
        self.assertIsNone(endpoint.product)

    def test_url_full(self):
        endpoint = Endpoint.from_uri('http://alice@foo.bar:8080/path1/path2?key1=value&no_value_key#fragment1')
        self.assertEqual(endpoint.protocol, 'http')
        self.assertEqual(endpoint.userinfo, 'alice')
        self.assertEqual(endpoint.host, 'foo.bar')
        self.assertEqual(endpoint.port, 8080)
        self.assertEqual(endpoint.path, 'path1/path2')  # path begins with '/' but Endpoint store "root-less" path
        self.assertEqual(endpoint.query, 'key1=value&no_value_key')
        self.assertEqual(endpoint.fragment, 'fragment1')

    def test_truncates_large_attributes(self):
        path = "foo" * 1000
        query = "bar" * 1000
        fragment = "baz" * 1000
        endpoint = Endpoint.from_uri('http://alice@foo.bar:8080/{}?{}#{}'.format(path, query, fragment))
        self.assertEqual(len(endpoint.path), 500)
        self.assertEqual(len(endpoint.query), 1000)
        self.assertEqual(len(endpoint.fragment), 500)

    def test_noscheme(self):
        endpoint = Endpoint.from_uri('//' + 'localhost:22')
        self.assertIsNone(endpoint.protocol)
        self.assertIsNone(endpoint.userinfo)
        self.assertEqual(endpoint.host, 'localhost')
        self.assertEqual(endpoint.port, 22)
        self.assertIsNone(endpoint.path)
        self.assertIsNone(endpoint.query)
        self.assertIsNone(endpoint.fragment)
        self.assertIsNone(endpoint.product)

    def test_paths(self):
        endpoint = Endpoint.from_uri('https://foo.bar')
        self.assertIsNone(endpoint.path)
        endpoint = Endpoint.from_uri('https://foo.bar/')
        self.assertIsNone(endpoint.path)

    def test_ip(self):
        endpoint = Endpoint.from_uri('http://127.0.0.1/')
        self.assertEqual(endpoint.host, '127.0.0.1')
        endpoint = Endpoint(host='127.0.0.1')
        self.assertEqual(endpoint.host, '127.0.0.1')

    def test_less_standard_hosts(self):
        endpoint = Endpoint.from_uri('http://123_server/')
        endpoint.clean()
        endpoint = Endpoint(host='456_desktop')
        endpoint.clean()
        endpoint = Endpoint(host='_invalid._host.com')
        endpoint.clean()

    def test_invalid(self):
        self.assertRaises(ValidationError, Endpoint.from_uri, 'http://127.0.0.1:portNo/')
        endpoint = Endpoint.from_uri('http://127.0.0.1:-1/')
        self.assertRaises(ValidationError, endpoint.clean)
        endpoint = Endpoint.from_uri('http://127.0.0.1:66666/')
        self.assertRaises(ValidationError, endpoint.clean)
        endpoint = Endpoint(host='127.0.0.1', port=-1)
        self.assertRaises(ValidationError, endpoint.clean)
        endpoint = Endpoint(host='127.0.0.1', port=66666)
        self.assertRaises(ValidationError, endpoint.clean)

    def test_ports(self):
        # known port
        endpoint = Endpoint.from_uri('http://foo.bar/')
        self.assertEqual(endpoint.port, 80)
        # unknown port
        endpoint = Endpoint.from_uri('this-scheme-is-unknown://foo.bar/')
        self.assertIsNone(endpoint.port)

    def test_spacial_char(self):
        endpoint = Endpoint.from_uri('http://foo.bar/beforeSpace%20afterSpace')
        self.assertEqual(endpoint.path, 'beforeSpace afterSpace')
        self.assertEqual(str(endpoint), 'http://foo.bar/beforeSpace%20afterSpace')
        endpoint = Endpoint.from_uri('//' + 'foo.bar/beforeSpace%20afterSpace')
        self.assertEqual(endpoint.path, 'beforeSpace afterSpace')
        self.assertEqual(str(endpoint), 'foo.bar/beforeSpace%20afterSpace')

    def test_url_normalize(self):
        endpoint1 = Endpoint.from_uri('HTTP://FOO.BAR/')
        endpoint2 = Endpoint.from_uri('HtTp://foo.BAR/')
        self.assertEqual(endpoint1.protocol, 'HTTP')
        self.assertEqual(endpoint1.host, 'foo.bar')
        self.assertEqual(str(endpoint1), 'http://foo.bar')
        self.assertEqual(endpoint1, endpoint2)

    def test_get_or_create(self):
        endpoint1, created1 = endpoint_get_or_create(
            protocol='http',
            host='bar.foo'
        )
        self.assertTrue(created1)

        endpoint2, created2 = endpoint_get_or_create(
            protocol='http',
            host='bar.foo'
        )
        self.assertFalse(created2)

        endpoint3, created3 = endpoint_get_or_create(
            protocol='http',
            host='bar.foo',
            port=80
        )
        self.assertFalse(created3)

        endpoint4, created4 = endpoint_get_or_create(
            protocol='http',
            host='bar.foo',
            port=8080
        )
        self.assertTrue(created4)

        endpoint5, created5 = endpoint_get_or_create(
            protocol='https',
            host='bar.foo',
            port=443
        )
        self.assertTrue(created5)

        endpoint6, created6 = endpoint_get_or_create(
            protocol='https',
            host='bar.foo'
        )
        self.assertFalse(created6)

        endpoint7, created7 = endpoint_get_or_create(
            protocol='https',
            host='bar.foo',
            port=8443
        )
        self.assertTrue(created7)


# TODO: These tests can be skipped in the future (when Endpoint_Status.{finding,endpoint}(null=False,blank=False))
# @skip("Outdated - this class was testing clean-up broken entries in old version of model; new version of model doesn't to store broken entries")
class TestEndpointStatusBrokenModel(DojoTestCase):

    def test_endpoint_status_broken(self):

        self.prod_type = Product_Type.objects.create()
        self.product = Product.objects.create(prod_type=self.prod_type)
        self.engagement = Engagement.objects.create(
            product=self.product,
            target_start=datetime.datetime(2020, 1, 1, tzinfo=timezone.utc),
            target_end=datetime.datetime(2022, 1, 1, tzinfo=timezone.utc)
        )
        self.test = Test.objects.create(
            engagement=self.engagement,
            target_start=datetime.datetime(2020, 1, 1, tzinfo=timezone.utc),
            target_end=datetime.datetime(2022, 1, 1, tzinfo=timezone.utc),
            test_type_id=1
        )
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create().pk
        self.finding = Finding.objects.create(test=self.test, reporter_id=user).pk
        self.endpoint = Endpoint.objects.create(protocol='http', host='foo.bar.eps').pk
        self.another_finding = Finding.objects.create(test=self.test, reporter_id=user).pk
        self.another_endpoint = Endpoint.objects.create(protocol='http', host='bar.foo.eps').pk
        self.endpoint_status = {
            'standard': Endpoint_Status.objects.create(
                date=datetime.datetime(2021, 3, 1, tzinfo=timezone.utc),
                last_modified=datetime.datetime(2021, 4, 1, tzinfo=timezone.utc),
                mitigated=False,
                finding_id=self.finding,
                endpoint_id=self.endpoint
            ).pk,
            'removed_endpoint': Endpoint_Status.objects.create(
                date=datetime.datetime(2021, 2, 1, tzinfo=timezone.utc),
                last_modified=datetime.datetime(2021, 5, 1, tzinfo=timezone.utc),
                mitigated=True,
                finding_id=self.another_finding,
                endpoint_id=None
            ).pk,
            'removed_finding': Endpoint_Status.objects.create(
                date=datetime.datetime(2021, 2, 1, tzinfo=timezone.utc),
                last_modified=datetime.datetime(2021, 5, 1, tzinfo=timezone.utc),
                mitigated=True,
                finding_id=None,
                endpoint_id=self.another_endpoint
            ).pk,
        }

        Finding.objects.get(id=self.finding).endpoint_status.add(
            Endpoint_Status.objects.get(id=self.endpoint_status['standard'])
        )
        Finding.objects.get(id=self.another_finding).endpoint_status.add(
            Endpoint_Status.objects.get(id=self.endpoint_status['removed_endpoint'])
        )

        Endpoint.objects.get(id=self.endpoint).endpoint_status.add(
            Endpoint_Status.objects.get(id=self.endpoint_status['standard'])
        )
        Endpoint.objects.get(id=self.another_endpoint).endpoint_status.add(
            Endpoint_Status.objects.get(id=self.endpoint_status['removed_finding'])
        )

        remove_broken_endpoint_statuses(apps)

        with self.subTest('Stadnard eps for finding'):
            f = Finding.objects.filter(id=self.finding)
            self.assertEqual(f.count(), 1)
            f = f.first()
            self.assertEqual(f.endpoint_status.count(), 1)
            self.assertEqual(f.endpoint_status.first().pk, self.endpoint_status['standard'])

        with self.subTest('Broken eps for finding'):
            f = Finding.objects.filter(id=self.another_finding)
            self.assertEqual(f.count(), 1)
            f = f.first()
            self.assertEqual(f.endpoint_status.count(), 0)

        with self.subTest('Stadnard eps for endpoint'):
            e = Endpoint.objects.filter(id=self.endpoint)
            self.assertEqual(e.count(), 1)
            e = e.first()
            self.assertEqual(e.endpoint_status.count(), 1)
            self.assertEqual(e.endpoint_status.first().pk, self.endpoint_status['standard'])

        with self.subTest('Broken eps for endpoint'):
            e = Endpoint.objects.filter(id=self.another_endpoint)
            self.assertEqual(e.count(), 1)
            e = e.first()
            self.assertEqual(e.endpoint_status.count(), 0)
