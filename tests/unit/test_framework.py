"""Offline regressions: no backend or database is contacted."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

import conftest as fixtures
import main as runner
from util.api_setup import ApiResource, create_product, replace_path_id, response_json
from util.assert_util import assert_response
from util.yaml_util import YamlUtil


def response(body, status=200):
    return SimpleNamespace(status_code=status, json=lambda: body)


def test_response_checks_http_even_when_business_body_matches():
    with pytest.raises(AssertionError, match="HTTP 状态码"):
        assert_response(response({"code": 0}, 500), {"code": 0})


def test_http_failure_includes_business_error_without_response_data():
    resp = response(
        {"code": 400, "msg": "商品主图不能为空", "data": {"token": "private-token"}},
        400,
    )
    with pytest.raises(AssertionError) as failure:
        assert_response(resp, {"code": 0})
    message = str(failure.value)
    assert "code=400" in message
    assert "商品主图不能为空" in message
    assert "private-token" not in message


@pytest.mark.parametrize(
    "body, message", [([], "根节点"), ({}, "缺少字段"), ({"code": 1}, "预期 0")]
)
def test_response_reports_useful_failures(body, message):
    with pytest.raises(AssertionError, match=message):
        assert_response(response(body), {"code": 0})


def test_non_json_response_is_an_assertion_failure():
    broken = Mock(status_code=200)
    broken.json.side_effect = ValueError("not json")
    with pytest.raises(AssertionError, match="有效 JSON"):
        assert_response(broken, {"code": 0})


def test_response_supports_explicit_status_and_parses_once():
    resp = Mock(status_code=201)
    resp.json.return_value = {"code": 0, "msg": "success"}
    assert assert_response(resp, {"status_code": 201, "code": 0})["msg"] == "success"
    resp.json.assert_called_once()


def test_fixture_setup_rejects_business_errors():
    with pytest.raises(AssertionError, match="响应字段 code"):
        response_json(response({"code": 11001, "msg": "login failed"}))


def test_path_replacement_copies_request_and_matches_segments():
    request = {"url": "http://test/api/products/17/images/117", "json": {"id": 17}}
    original = deepcopy(request)
    result = replace_path_id(request, 17, 42)
    assert result["url"] == "http://test/api/products/42/images/117"
    result["json"]["id"] = 9
    assert request == original


def test_yaml_context_types_environment_precedence_and_copy(tmp_path, monkeypatch):
    source = tmp_path / "case.yaml"
    source.write_text(
        'url: "${API_BASE_URL}/api"\nid: "{{ id }}"\npayload: [1]\nfallback: "${UNSET_CASE_VALUE:-local}"\n'
    )
    monkeypatch.setenv("API_BASE_URL", "https://ci.test")
    monkeypatch.delenv("UNSET_CASE_VALUE", raising=False)
    loader = YamlUtil(source)
    result = loader.read_yaml({"API_BASE_URL": "https://context.test", "id": 42})
    assert result["url"] == "https://ci.test/api"
    assert result["id"] == 42
    assert result["fallback"] == "local"
    result["payload"].append(2)
    assert loader.read_yaml({"id": 43})["payload"] == [1]


def test_yaml_external_edits_invalidate_cache(tmp_path):
    source = tmp_path / "case.yaml"
    source.write_text("value: old\n")
    loader = YamlUtil(source)
    assert loader.read_yaml()["value"] == "old"
    source.write_text("value: changed\n")
    assert loader.read_yaml()["value"] == "changed"


def test_yaml_unknown_variables_fail_before_requests(tmp_path):
    source = tmp_path / "case.yaml"
    source.write_text('value: "{{ missing_case_variable }}"\n')
    with pytest.raises(KeyError, match="missing_case_variable"):
        YamlUtil(source).read_yaml()


@pytest.mark.parametrize(
    "data, message",
    [
        ({}, "非空列表"),
        ({"cases": [1]}, "用例必须是对象"),
        ({"cases": [{"title": ""}]}, "title"),
        ({"cases": [{"title": "test", "request": {}}]}, "method"),
        ({"cases": [{"title": "test", "request": {"method": "GET"}}]}, "expected"),
        (
            {
                "ids": [],
                "cases": [
                    {
                        "title": "test",
                        "request": {"method": "GET"},
                        "expected": {"code": 0, "msg": "success"},
                    }
                ],
            },
            "数量不一致",
        ),
    ],
)
def test_yaml_schema_errors_identify_the_file(tmp_path, data, message):
    source = tmp_path / "invalid.yaml"
    source.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match=message) as error:
        YamlUtil(source).read_cases()
    assert str(source) in str(error.value)


def test_all_case_documents_are_valid():
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "data").rglob("*.yaml"))
    assert paths
    for path in paths:
        cases, ids = YamlUtil(path).read_cases()
        assert len(cases) == len(ids)


@pytest.mark.parametrize("code", [pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED])
def test_runner_handles_missing_allure_and_restores_directory(
    monkeypatch, tmp_path, code, capsys
):
    monkeypatch.chdir(tmp_path)
    calls = []

    def run_pytest(args, plugins):
        calls.append((Path.cwd(), args))
        return code

    monkeypatch.setattr(pytest, "main", run_pytest)
    monkeypatch.setattr(
        runner.subprocess, "run", Mock(side_effect=FileNotFoundError("allure"))
    )
    assert runner.main(["-m", "smoke"]) == 1
    assert Path.cwd() == tmp_path
    assert calls == [
        (Path(runner.__file__).parent, ["--clean-alluredir", "-m", "smoke"])
    ]
    assert "--no-report" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args, code",
    [
        (["--no-report"], pytest.ExitCode.OK),
        (["--collect-only"], pytest.ExitCode.OK),
        ([], pytest.ExitCode.USAGE_ERROR),
        ([], pytest.ExitCode.NO_TESTS_COLLECTED),
        ([], pytest.ExitCode.INTERRUPTED),
    ],
)
def test_runner_skips_html_when_not_needed(monkeypatch, tmp_path, args, code):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pytest, "main", Mock(return_value=code))
    generate = Mock()
    monkeypatch.setattr(runner.subprocess, "run", generate)
    assert runner.main(args) == code
    generate.assert_not_called()
    assert Path.cwd() == tmp_path


def test_runner_keeps_original_failure_when_report_generation_fails(monkeypatch):
    monkeypatch.setattr(pytest, "main", Mock(return_value=pytest.ExitCode.TESTS_FAILED))
    monkeypatch.setattr(
        runner.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=7))
    )
    assert runner.main([]) == pytest.ExitCode.TESTS_FAILED


def test_missing_database_does_not_fail_api_only_selection(monkeypatch):
    monkeypatch.setattr(
        fixtures, "settings", SimpleNamespace(has_database_password=False)
    )
    config = SimpleNamespace(
        stash=pytest.Stash(), option=SimpleNamespace(collectonly=False)
    )
    item = SimpleNamespace(fixturenames=["http_client"])
    session = SimpleNamespace(
        config=config, items=[item], exitstatus=pytest.ExitCode.OK
    )
    fixtures.pytest_collection_finish(session)
    fixtures.pytest_sessionfinish(session, pytest.ExitCode.OK)
    assert session.exitstatus == pytest.ExitCode.OK


def test_missing_database_is_reported_for_selected_database_tests(monkeypatch):
    monkeypatch.setattr(
        fixtures, "settings", SimpleNamespace(has_database_password=False)
    )
    config = SimpleNamespace(
        stash=pytest.Stash(), option=SimpleNamespace(collectonly=False)
    )
    item = SimpleNamespace(fixturenames=["db"], add_marker=Mock())
    session = SimpleNamespace(
        config=config, items=[item], exitstatus=pytest.ExitCode.OK
    )
    fixtures.pytest_collection_finish(session)
    fixtures.pytest_sessionfinish(session, pytest.ExitCode.OK)
    item.add_marker.assert_called_once()
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED


def test_address_fixture_creates_and_cleans_up_its_own_address(monkeypatch):
    client = Mock()
    client.send_all_request.side_effect = [
        response({"code": 0, "data": [{"addressId": 9, "isDefault": True}]}),
        response({"code": 0, "data": {"addressId": 42}}),
        response({"code": 0}),
        response({"code": 0}),
    ]
    cleanup = fixtures.address_cleanup.__wrapped__(client, "user-token")
    register = next(cleanup)
    address = fixtures.address_resource.__wrapped__(client, "user-token", register)
    assert address.resource_id == 42
    with pytest.raises(StopIteration):
        next(cleanup)
    requests = [call.kwargs for call in client.send_all_request.call_args_list]
    assert requests[2]["method"] == "DELETE"
    assert requests[2]["url"].endswith("/addresses/42")
    assert requests[3]["url"].endswith("/addresses/9/default")


def test_fixture_product_contains_required_main_image():
    client = Mock()
    client.send_all_request.return_value = response(
        {"code": 0, "data": {"productId": 42}}
    )
    product = create_product(client, "admin-token")
    assert product.resource_id == 42
    assert client.send_all_request.call_args.kwargs["json"]["mainImageUrl"]


def test_product_creation_cases_reach_business_validation():
    root = Path(__file__).resolve().parents[2]
    cases, _ = YamlUtil(root / "data/product/product_create_product.yaml").read_cases()
    for case in cases:
        assert case["request"]["json"]["mainImageUrl"]


def test_order_setup_uses_new_address_and_cleans_cart():
    client = Mock()
    client.send_all_request.side_effect = [
        response({"code": 0}),
        response({"code": 0}),
        response({"code": 0, "data": {"orderId": 123}}),
        response({"code": 0}),
    ]
    scenario = fixtures._create_order_via_api(client, ApiResource("user-token", 42))
    assert scenario.order_id == 123
    requests = [call.kwargs for call in client.send_all_request.call_args_list]
    assert requests[2]["json"]["addressId"] == 42
    assert requests[2]["token"] == "user-token"
    assert requests[-1]["method"] == "DELETE"
    assert requests[-1]["url"].endswith("/cart/items/101")


def test_failed_order_setup_still_cleans_cart():
    client = Mock()
    client.send_all_request.side_effect = [
        response({"code": 0}),
        response({"code": 0}),
        response({"code": 15004, "msg": "收货地址不存在"}, 400),
        response({"code": 0}),
    ]
    with pytest.raises(AssertionError, match="收货地址不存在"):
        fixtures._create_order_via_api(client, ApiResource("user-token", 42))
    assert client.send_all_request.call_args.kwargs["method"] == "DELETE"


def test_order_address_fixture_cleans_the_address_it_created():
    client = Mock()
    client.send_all_request.side_effect = [
        response({"code": 0, "data": {"token": "user-token"}}),
        response({"code": 0, "data": {"addressId": 42}}),
        response({"code": 0}),
    ]
    fixture = fixtures.order_address.__wrapped__(client)
    address = next(fixture)
    assert address == ApiResource("user-token", 42)
    with pytest.raises(StopIteration):
        next(fixture)
    cleanup = client.send_all_request.call_args.kwargs
    assert cleanup["method"] == "DELETE"
    assert cleanup["url"].endswith("/addresses/42")


@pytest.mark.parametrize("code", [0, 13001, 13002, 13004])
def test_inventory_setup_only_initializes_for_duplicate_case(code):
    client = Mock()
    client.send_all_request.return_value = response({"code": 0})
    product = ApiResource("admin-token", 42)
    result = fixtures.init_inventory.__wrapped__(
        client, product, {"expected": {"code": code}}
    )
    assert result is product
    if code == 13004:
        setup = client.send_all_request.call_args.kwargs
        assert setup["json"] == {"productId": 42, "quantity": 10}
    else:
        client.send_all_request.assert_not_called()


def test_restock_setup_initializes_only_the_disposable_product():
    client = Mock()
    client.send_all_request.return_value = response({"code": 0})
    product = ApiResource("admin-token", 42)
    assert fixtures.restock_inventory.__wrapped__(client, product) is product
    assert client.send_all_request.call_args.kwargs["json"] == {
        "productId": 42,
        "quantity": 10,
    }
