"""Tests for the temporary module entry point."""

from admin_helper.__main__ import main


def test_main_reports_not_implemented(capsys) -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: main reports not implemented.
    """
    main()

    captured = capsys.readouterr()
    assert captured.out == "admin-helper is not implemented yet.\n"
    assert captured.err == ""
