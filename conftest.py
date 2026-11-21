from __future__ import annotations

import logging

import pytest
from jsonpath import jsonpath

from settings import settings
from util.api_setup import (
    ApiResource,
    OrderScenario,
    create_product,
    create_category,
    delete_resource,
    api_url,
    response_json,
    response_value,
)
from util.request_util import RequestUtil
from util.sql_util import SqlUtil
from util.allure_util import Allure_util

logger = logging.getLogger(__name__)
_DB_CONFIG_ERROR = pytest.StashKey[str]()


def pytest_sessionfinish(session, exitstatus):
    """Release HTTP resources even when no fixture requested ``http_client``."""
    RequestUtil.close_shared_session()
    if (
        session.config.stash.get(_DB_CONFIG_ERROR, "")
        and exitstatus == pytest.ExitCode.OK
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_collection_finish(session):
    """Keep API-only tests useful while reporting missing DB configuration once."""
    config = session.config
    if settings.has_database_password or config.option.collectonly:
        return
    items = [item for item in session.items if "db" in item.fixturenames]
    if not items:
        return
    message = (
        "数据库测试未执行：未配置 DB_PASSWORD。请复制 .env.example 为 .env 并填写，"
        "或设置 DB_PASSWORD 环境变量。"
    )
    config.stash[_DB_CONFIG_ERROR] = message
    marker = pytest.mark.skip(reason=message)
    for item in items:
        item.add_marker(marker)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    message = config.stash.get(_DB_CONFIG_ERROR, "")
    if message:
        terminalreporter.write_sep("!", message, yellow=True)


@pytest.fixture(autouse=True)
def case_metadata(request):
    """Keep logging and Allure labels consistent for every YAML case."""
    if "case_info" in request.fixturenames:
        case_info = request.getfixturevalue("case_info")
        Allure_util.set_allure(case_info)
        logger.info(
            "测试用例开始执行：%s：%s", request.node.originalname, case_info["title"]
        )


USER_LOGIN = {
    "method": "POST",
    "url": f"{settings.api_base_url}/api/users/login",
    "json": {"phone": settings.user_phone, "password": settings.user_password},
}
ADMIN_LOGIN = {
    "method": "POST",
    "url": f"{settings.api_base_url}/api/users/login",
    "json": {"phone": settings.admin_phone, "password": settings.admin_password},
}
CART_ITEM = {
    "method": "POST",
    "url": f"{settings.api_base_url}/api/cart/items",
    "json": {"productId": 101, "quantity": 1},
}


def _login(client: RequestUtil, login_info: dict) -> str:
    response = client.send_all_request(**login_info)
    return response_value(response, "$.data.token")


@pytest.fixture(scope="session")
def http_client():
    client = RequestUtil()
    try:
        yield client
    finally:
        RequestUtil.close_shared_session()


@pytest.fixture(scope="session")
def db():
    settings.validate_database()
    database = SqlUtil(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )
    try:
        database.connect()
        yield database
    finally:
        database.close()


@pytest.fixture(scope="function")
def user_token(http_client):
    return _login(http_client, USER_LOGIN)


@pytest.fixture(scope="function")
def admin_token(http_client):
    return _login(http_client, ADMIN_LOGIN)


@pytest.fixture(scope="function")
def change_pwd_user(http_client):
    token = _login(http_client, USER_LOGIN)
    try:
        yield token
    finally:
        # Restore a successful password-change case through the user API. If
        # the case failed validation, the original password remains active.
        changed_login = {
            "method": "POST",
            "url": api_url("/api/users/login"),
            "json": {"phone": settings.user_phone, "password": "Test12345"},
        }
        response = http_client.send_all_request(**changed_login)
        tokens = (
            jsonpath(response.json(), "$..token") if response.status_code == 200 else []
        )
        if tokens:
            http_client.send_all_request(
                method="PUT",
                url=api_url("/api/users/password"),
                token=tokens[0],
                json={
                    "oldPassword": "Test12345",
                    "newPassword": settings.user_password,
                    "confirmPassword": settings.user_password,
                },
            )


@pytest.fixture(scope="function")
def registered_user_cleanup(db):
    """Remove users created by registration tests after the assertion."""
    phones = []
    try:
        yield phones.append
    finally:
        for phone in phones:
            db.execute_sql("DELETE FROM user WHERE phone = %s", (phone,))


@pytest.fixture(scope="function")
def del_category(http_client):
    """Create/delete the category through the admin API.

    The old fixture inserted a fixed primary key directly into MySQL. The API
    owns ID generation, so the success case receives the generated ID through
    this resource object.
    """
    resource = create_category(http_client, _login(http_client, ADMIN_LOGIN))
    try:
        yield resource
    finally:
        delete_resource(
            http_client,
            "DELETE",
            f"/api/admin/categories/{resource.resource_id}",
            resource.token,
        )


@pytest.fixture(scope="function")
def deletable_product(http_client, admin_token):
    """Create a disposable OFF_SALE product through the admin API."""
    resource = create_product(http_client, admin_token)
    try:
        yield resource
    finally:
        http_client.send_all_request(
            method="PUT",
            url=api_url(f"/api/admin/products/{resource.resource_id}/off-sale"),
            token=resource.token,
        )
        delete_resource(
            http_client,
            "DELETE",
            f"/api/admin/products/{resource.resource_id}",
            resource.token,
        )


@pytest.fixture(scope="function")
def product_image_resource(http_client, admin_token):
    """Create a disposable product image through the admin API."""
    product_id = 116
    response = http_client.send_all_request(
        method="POST",
        url=api_url(f"/api/admin/products/{product_id}/images"),
        json={
            "url": "https://example.test/fixture-image.jpg",
            "type": "DETAIL",
            "sort": 99,
        },
        token=admin_token,
    )
    image_id = int(response_value(response, "$..imageId"))
    try:
        yield ApiResource(admin_token, image_id)
    finally:
        delete_resource(
            http_client,
            "DELETE",
            f"/api/admin/products/{product_id}/images/{image_id}",
            admin_token,
        )


@pytest.fixture(scope="function")
def on_sale_product(http_client, admin_token):
    """Create a product and transition it through the sale API."""
    resource = create_product(http_client, admin_token)
    response_json(
        http_client.send_all_request(
            method="PUT",
            url=api_url(f"/api/admin/products/{resource.resource_id}/on-sale"),
            token=admin_token,
        )
    )
    try:
        yield resource
    finally:
        # The source API requires OFF_SALE before DELETE.
        http_client.send_all_request(
            method="PUT",
            url=api_url(f"/api/admin/products/{resource.resource_id}/off-sale"),
            token=admin_token,
        )
        delete_resource(
            http_client,
            "DELETE",
            f"/api/admin/products/{resource.resource_id}",
            admin_token,
        )


@pytest.fixture
def init_inventory(http_client, deletable_product, case_info):
    """A fresh product provides zero stock without resetting existing records."""
    if case_info["expected"]["code"] == 13004:
        response_json(
            http_client.send_all_request(
                method="POST",
                url=api_url("/api/admin/inventory"),
                json={"productId": deletable_product.resource_id, "quantity": 10},
                token=deletable_product.token,
            )
        )
    return deletable_product


@pytest.fixture
def restock_inventory(http_client, deletable_product):
    """Restock an isolated product instead of increasing seed stock each run."""
    response_json(
        http_client.send_all_request(
            method="POST",
            url=api_url("/api/admin/inventory"),
            json={"productId": deletable_product.resource_id, "quantity": 10},
            token=deletable_product.token,
        )
    )
    return deletable_product


def _create_order_via_api(client: RequestUtil, address: ApiResource) -> OrderScenario:
    """Create a pending order by following the real cart/order workflow."""
    user_token = address.token
    item_url = api_url("/api/cart/items/101")
    # DELETE is idempotent for this setup; an empty cart is a valid state.
    client.send_all_request(method="DELETE", url=item_url, token=user_token)
    try:
        added = client.send_all_request(token=user_token, **CART_ITEM)
        response_json(added)
        created = client.send_all_request(
            method="POST",
            url=api_url("/api/orders"),
            json={"productIds": [101], "addressId": address.resource_id},
            token=user_token,
        )
        order_id = int(response_value(created, "$..orderId"))
    finally:
        client.send_all_request(method="DELETE", url=item_url, token=user_token)
    return OrderScenario(token=user_token, user_token=user_token, order_id=order_id)


def _order_action(
    client: RequestUtil, scenario: OrderScenario, path: str, *, admin=False
):
    token = _login(client, ADMIN_LOGIN) if admin else scenario.user_token
    response = client.send_all_request(method="PUT", url=api_url(path), token=token)
    response_json(response)
    return token


@pytest.fixture(scope="class")
def create_order(http_client, order_address):
    token = order_address.token
    item_url = api_url("/api/cart/items/101")
    http_client.send_all_request(method="DELETE", url=item_url, token=token)
    response_json(http_client.send_all_request(token=token, **CART_ITEM))
    try:
        yield order_address
    finally:
        http_client.send_all_request(method="DELETE", url=item_url, token=token)


ORDER_ADDRESS = {
    "city": "北京市",
    "detail": "建国路88号",
    "district": "朝阳区",
    "province": "北京市",
    "receiverName": "李四",
    "receiverPhone": "13987654321",
}


@pytest.fixture(scope="class")
def order_address(http_client):
    """Use an address owned by this test user, independent of seed IDs."""
    token = _login(http_client, USER_LOGIN)
    response = http_client.send_all_request(
        method="POST",
        url=api_url("/api/users/addresses"),
        token=token,
        json={**ORDER_ADDRESS, "isDefault": False},
    )
    address_id = int(response_value(response, "$.data.addressId"))
    try:
        yield ApiResource(token, address_id)
    finally:
        delete_resource(
            http_client, "DELETE", f"/api/users/addresses/{address_id}", token
        )


@pytest.fixture
def address_cleanup(http_client, user_token):
    """Track addresses and restore the original default after each case."""
    body = response_json(
        http_client.send_all_request(
            method="GET",
            url=api_url("/api/users/addresses"),
            token=user_token,
        )
    )
    default_ids = [item["addressId"] for item in body["data"] if item.get("isDefault")]
    address_ids = []
    try:
        yield address_ids.append
    finally:
        for address_id in address_ids:
            delete_resource(
                http_client, "DELETE", f"/api/users/addresses/{address_id}", user_token
            )
        for address_id in default_ids:
            response_json(
                http_client.send_all_request(
                    method="PUT",
                    url=api_url(f"/api/users/addresses/{address_id}/default"),
                    token=user_token,
                )
            )


@pytest.fixture
def address_resource(http_client, user_token, address_cleanup):
    response = http_client.send_all_request(
        method="POST",
        url=api_url("/api/users/addresses"),
        token=user_token,
        json={**ORDER_ADDRESS, "isDefault": False},
    )
    address_id = int(response_value(response, "$.data.addressId"))
    address_cleanup(address_id)
    return ApiResource(user_token, address_id)


@pytest.fixture(scope="class")
def cancel_order(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    try:
        yield scenario
    finally:
        http_client.send_all_request(
            method="PUT",
            url=api_url(f"/api/orders/{scenario.order_id}/cancel"),
            token=scenario.user_token,
            json={"cancelReason": "fixture cleanup"},
        )


@pytest.fixture(scope="class")
def pay_order(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    try:
        yield scenario
    finally:
        # Negative cases leave the order pending; clean that state through the
        # business API. A paid order has no reverse endpoint in the source.
        http_client.send_all_request(
            method="PUT",
            url=api_url(f"/api/orders/{scenario.order_id}/cancel"),
            token=scenario.user_token,
            json={"cancelReason": "fixture cleanup"},
        )


@pytest.fixture(scope="class")
def ship_order(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    _order_action(http_client, scenario, f"/api/orders/{scenario.order_id}/pay")
    scenario.token = _login(http_client, ADMIN_LOGIN)
    yield scenario


@pytest.fixture(scope="class")
def confirm_order(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    _order_action(http_client, scenario, f"/api/orders/{scenario.order_id}/pay")
    scenario.token = _order_action(
        http_client, scenario, f"/api/admin/orders/{scenario.order_id}/ship", admin=True
    )
    scenario.token = scenario.user_token
    yield scenario


@pytest.fixture(scope="class")
def refund_create(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    _order_action(http_client, scenario, f"/api/orders/{scenario.order_id}/pay")
    yield scenario


@pytest.fixture(scope="class")
def approve_refund(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    _order_action(http_client, scenario, f"/api/orders/{scenario.order_id}/pay")
    refund = http_client.send_all_request(
        method="POST",
        url=api_url(f"/api/orders/{scenario.order_id}/refunds"),
        json={"reason": "fixture refund"},
        token=scenario.user_token,
    )
    scenario.refund_id = int(response_value(refund, "$..refundId"))
    scenario.token = _login(http_client, ADMIN_LOGIN)
    yield scenario


@pytest.fixture(scope="class")
def reject_refund(http_client, order_address):
    scenario = _create_order_via_api(http_client, order_address)
    _order_action(http_client, scenario, f"/api/orders/{scenario.order_id}/pay")
    refund = http_client.send_all_request(
        method="POST",
        url=api_url(f"/api/orders/{scenario.order_id}/refunds"),
        json={"reason": "fixture refund"},
        token=scenario.user_token,
    )
    scenario.refund_id = int(response_value(refund, "$..refundId"))
    scenario.token = _login(http_client, ADMIN_LOGIN)
    yield scenario
