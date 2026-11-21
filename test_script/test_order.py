from copy import deepcopy
import pytest
from pathlib import Path

from util.api_setup import api_url, replace_path_id, response_value
from util.case_util import case_parametrize
from util.assert_util import assert_response

case_path = str(Path(__file__).parent.parent / "data" / "order")


class TestOrder:

    @pytest.mark.order
    @case_parametrize(case_path + "/order_create.yaml")
    def test_create_order(self, case_info, create_order, http_client):

        request = deepcopy(case_info["request"])
        request["json"]["addressId"] = create_order.resource_id
        resp = http_client.send_all_request(token=create_order.token, **request)
        order_id = (
            response_value(resp, "$.data.orderId")
            if resp.json().get("code") == 0
            else None
        )
        try:
            assert_response(resp, case_info["expected"])
        finally:
            if order_id is not None:
                http_client.send_all_request(
                    method="PUT",
                    url=api_url(f"/api/orders/{order_id}/cancel"),
                    token=create_order.token,
                    json={"cancelReason": "fixture cleanup"},
                )

    @pytest.mark.order
    @case_parametrize(case_path + "/order_check.yaml")
    def test_check_order(self, case_info, user_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=user_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_check_detail.yaml")
    def test_check_order_detail(self, case_info, user_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=user_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_cancel.yaml")
    def test_order_cancel(self, case_info, cancel_order, http_client):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 10, cancel_order.order_id)
        resp = http_client.send_all_request(token=cancel_order.token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_pay.yaml")
    def test_order_pay(self, case_info, pay_order, http_client):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 11, pay_order.order_id)
        resp = http_client.send_all_request(token=pay_order.token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_ship.yaml")
    def test_order_ship(self, case_info, ship_order, http_client):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 12, ship_order.order_id)
        resp = http_client.send_all_request(token=ship_order.token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_confirm.yaml")
    def test_order_confirm(self, case_info, confirm_order, http_client):

        request = case_info["request"]
        if case_info["expected"]["code"] == 0:
            request = replace_path_id(request, 13, confirm_order.order_id)
        resp = http_client.send_all_request(token=confirm_order.token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_status.yaml")
    def test_order_status(self, case_info, user_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=user_token, **request)

        assert_response(resp, case_info["expected"])

    @pytest.mark.order
    @case_parametrize(case_path + "/order_all_status.yaml")
    def test_order_all_status(self, case_info, admin_token, http_client):

        request = case_info["request"]
        resp = http_client.send_all_request(token=admin_token, **request)

        assert_response(resp, case_info["expected"])
