import pytest

from scripts.set_env_value import fingerprint, replace_assignment


def test_replaces_the_named_variable():
    content = "LOG_LEVEL=INFO\nDOI_PASSWORD=old\nPOSTGRES_PORT=5432\n"

    assert replace_assignment(content, "DOI_PASSWORD", "new") == (
        "LOG_LEVEL=INFO\nDOI_PASSWORD=new\nPOSTGRES_PORT=5432\n"
    )


def test_does_not_match_a_variable_that_merely_ends_with_the_name():
    content = "MINIO_SECRET_KEY=keep-me\nSECRET_KEY=replace-me\n"

    assert replace_assignment(content, "SECRET_KEY", "new") == (
        "MINIO_SECRET_KEY=keep-me\nSECRET_KEY=new\n"
    )


@pytest.mark.parametrize(
    "value",
    [
        "a&b",
        "a|b",
        "quote'and\"quote",
        "s.XZ4R9&Wj6'3*b@PNJC5m",
    ],
)
def test_writes_the_value_verbatim(value: str):
    content = "DOI_PASSWORD=old\n"

    assert replace_assignment(content, "DOI_PASSWORD", value) == (
        f"DOI_PASSWORD={value}\n"
    )


# The Makefile reads the environment file with `include`, so it is parsed as
# make syntax before any container sees it.
@pytest.mark.parametrize("value", ["with#hash", "with$dollar", "with`backtick`"])
def test_refuses_a_value_that_make_would_reinterpret(value: str):
    with pytest.raises(ValueError):
        replace_assignment("DOI_PASSWORD=old\n", "DOI_PASSWORD", value)


@pytest.mark.parametrize("value", [" leading", "trailing ", "\ttab"])
def test_refuses_surrounding_whitespace_that_a_parser_may_or_may_not_strip(value: str):
    with pytest.raises(ValueError):
        replace_assignment("DOI_PASSWORD=old\n", "DOI_PASSWORD", value)


def test_refuses_a_variable_that_is_not_already_there():
    with pytest.raises(KeyError):
        replace_assignment("LOG_LEVEL=INFO\n", "DOI_PASSWORD", "new")


def test_refuses_a_variable_assigned_twice_rather_than_guessing():
    content = "DOI_PASSWORD=one\nDOI_PASSWORD=two\n"

    with pytest.raises(ValueError):
        replace_assignment(content, "DOI_PASSWORD", "new")


def test_refuses_a_value_that_would_not_survive_the_file_format():
    with pytest.raises(ValueError):
        replace_assignment("DOI_PASSWORD=old\n", "DOI_PASSWORD", "two\nlines")


def test_keeps_a_file_that_does_not_end_in_a_newline_as_it_was():
    assert replace_assignment("DOI_PASSWORD=old", "DOI_PASSWORD", "new") == (
        "DOI_PASSWORD=new"
    )


def test_fingerprint_is_short_stable_and_not_the_value():
    assert fingerprint("hunter2") == fingerprint("hunter2")
    assert fingerprint("hunter2") != fingerprint("hunter3")
    assert len(fingerprint("hunter2")) == 8
    assert "hunter2" not in fingerprint("hunter2")
