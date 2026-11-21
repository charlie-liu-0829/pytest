from jsonpath import jsonpath
from decimal import Decimal
import pytest
from pathlib import Path

from util.api_setup import delete_resource, replace_path_id, response_value
from util.case_util import case_parametrize
from util.assert_util import assert_response

case_path = str(Path(__file__).parent.parent / "data" / "product")


class TestCategory:

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_create_category.yaml")
    def test_create_category(self, case_info, admin_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=admin_token, **request)

        if resp.json().get("code") == 0:
            cat_id = jsonpath(resp.json(), "$..categoryId")[0]
            delete_resource(
                http_client, "DELETE", f"/api/admin/categories/{cat_id}", admin_token
            )
        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_change_category.yaml")
    def test_change_category(self, case_info, admin_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_del_category.yaml")
    def test_del_category(self, case_info, del_category, http_client):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 10001, del_category.resource_id)
        resp = http_client.send_all_request(token=del_category.token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @pytest.mark.smoke
    @case_parametrize(case_path + "/product_get_category.yaml")
    def test_get_category(self, case_info, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(**request)

        assert_response(resp, case_info["expected"])


class TestProduct:
    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_create_product.yaml")
    def test_create_product(self, case_info, admin_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=admin_token, **request)

        if resp.json().get("code") == 0:
            product_id = jsonpath(resp.json(), "$..productId")[0]
            # Product creation defaults to OFF_SALE, so the business delete API
            # is the correct cleanup operation.
            delete_resource(
                http_client, "DELETE", f"/api/admin/products/{product_id}", admin_token
            )

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_change_product.yaml")
    def test_change_product(self, case_info, admin_token, http_client, request):

        api_request = case_info["request"]
        code = case_info["expected"]["code"]
        if code == 0:
            fixture = (
                "on_sale_product"
                if case_info.get("product_state") == "ON_SALE"
                else "deletable_product"
            )
            resource = request.getfixturevalue(fixture)
            api_request = replace_path_id(api_request, 116, resource.resource_id)
        resp = http_client.send_all_request(token=admin_token, **api_request)

        assert_response(resp, case_info["expected"])
        if code == 0:
            detail = http_client.send_all_request(
                method="GET",
                url=f"/api/products/{resource.resource_id}",
                token=admin_token,
            )
            actual = response_value(detail, "$.data.price")
            assert Decimal(str(actual)) == Decimal(str(api_request["json"]["price"]))
            if case_info.get("product_state") == "ON_SALE":
                assert response_value(detail, "$.data.status") == "ON_SALE"

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_on_sale.yaml")
    def test_on_sale(self, case_info, admin_token, http_client, deletable_product):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 117, deletable_product.resource_id)
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_off_sale.yaml")
    def test_off_sale(self, case_info, admin_token, http_client, on_sale_product):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 118, on_sale_product.resource_id)
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_del_product.yaml")
    def test_del_product(self, case_info, admin_token, http_client, deletable_product):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 119, deletable_product.resource_id)
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @pytest.mark.smoke
    @case_parametrize(case_path + "/product_search_product_list.yaml")
    def test_search_product_list(self, case_info, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(**request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @pytest.mark.smoke
    @case_parametrize(case_path + "/product_search_product.yaml")
    def test_search_product(self, case_info, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(**request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_add_product_image.yaml")
    def test_add_product_image(
        self, case_info, admin_token, http_client, deletable_product
    ):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 117, deletable_product.resource_id)
        resp = http_client.send_all_request(token=admin_token, **request)

        if resp.json().get("code") == 0:
            image_id = response_value(resp, "$..imageId")
            delete_resource(
                http_client,
                "DELETE",
                f"/api/admin/products/{deletable_product.resource_id}/images/{image_id}",
                admin_token,
            )

        assert_response(resp, case_info["expected"])

    @pytest.mark.productManagement
    @case_parametrize(case_path + "/product_del_product_image.yaml")
    def test_del_product_image(
        self, case_info, admin_token, http_client, product_image_resource
    ):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 117, 116)
            request = replace_path_id(request, 17, product_image_resource.resource_id)
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])
