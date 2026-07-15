import JLmain


def test_update_prompt_accepts_only_newer_server_version():
    assert JLmain._is_newer_version("V2.0.1 Premium", "V2.0.0 Premium") is True
    assert JLmain._is_newer_version("V2.1.0 Premium", "V2.0.9 Premium") is True


def test_update_prompt_rejects_equal_or_older_server_version():
    assert JLmain._is_newer_version("V2.0.0 Premium", "V2.0.0 Premium") is False
    assert JLmain._is_newer_version("V1.2.1 Premium", "V2.0.0 Premium") is False


def test_update_prompt_rejects_unparseable_versions():
    assert JLmain._is_newer_version("latest", "V2.0.0 Premium") is False
    assert JLmain._is_newer_version("V2.0.1 Premium", "development") is False
