from app.cli import main as cli_main


def test_create_user_then_list(capsys):
    rc = cli_main(["create-user", "--email", "cli@example.com", "--password", "x"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "created user cli@example.com" in out

    rc = cli_main(["list-users"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "cli@example.com" in out


def test_create_user_duplicate_email_fails(capsys):
    assert cli_main(["create-user", "--email", "dup@example.com", "--password", "x"]) == 0
    capsys.readouterr()
    rc = cli_main(["create-user", "--email", "dup@example.com", "--password", "y"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err


def test_set_password(capsys):
    from app.auth.passwords import verify_password
    from app.db import SessionLocal
    from app.models.user import User
    from sqlalchemy import select

    assert cli_main(["create-user", "--email", "pw@example.com", "--password", "old"]) == 0
    capsys.readouterr()

    assert cli_main(["set-password", "--email", "pw@example.com", "--password", "newpw"]) == 0

    with SessionLocal() as db:
        u = db.execute(select(User).where(User.email == "pw@example.com")).scalar_one()
        assert verify_password("newpw", u.password_hash)
        assert not verify_password("old", u.password_hash)


def test_set_password_unknown_user_fails():
    assert cli_main(["set-password", "--email", "ghost@example.com", "--password", "x"]) == 1
