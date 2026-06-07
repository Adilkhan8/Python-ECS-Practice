import json
import os
import re
import boto3
import pyodbc
from urllib.parse import urlparse

MDF_DOWNLOAD_DIR = "/var/opt/mssql/data"


def download_from_s3(s3_path: str, download_dir: str = MDF_DOWNLOAD_DIR) -> str:
    """Download an MDF or BAK file from S3 and return the local file path."""
    parsed = urlparse(s3_path)
    if parsed.scheme != "s3":
        raise ValueError(f"Invalid S3 path: {s3_path}")

    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    filename = os.path.basename(key)
    local_path = os.path.join(download_dir, filename)

    s3_client = boto3.client("s3")
    s3_client.download_file(bucket, key, local_path)
    print(f"Downloaded {s3_path} to {local_path}")
    return local_path


def _validate_identifier(name: str, label: str) -> None:
    """Reject identifiers that could be used for SQL injection."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,128}", name):
        raise ValueError(
            f"{label} contains invalid characters. "
            "Only alphanumerics, underscores, and hyphens are allowed."
        )


def _get_conn_str(sa_password: str) -> str:
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost;"
        "UID=SA;"
        f"PWD={sa_password};"
        "TrustServerCertificate=yes;"
    )


def attach_mdf(mdf_path: str, db_name: str, ldf_path: str = None) -> None:
    """Attach an MDF (and optionally an LDF) file to the local SQL Server instance."""
    sa_password = os.environ.get("SA_PASSWORD")
    if not sa_password:
        raise EnvironmentError("SA_PASSWORD environment variable is not set")

    # Validate inputs before embedding in DDL
    _validate_identifier(db_name, "DB_NAME")
    if not os.path.isabs(mdf_path) or not mdf_path.lower().endswith(".mdf"):
        raise ValueError(f"Unexpected MDF path: {mdf_path}")
    if ldf_path is not None and (
        not os.path.isabs(ldf_path) or not ldf_path.lower().endswith(".ldf")
    ):
        raise ValueError(f"Unexpected LDF path: {ldf_path}")

    conn_str = _get_conn_str(sa_password)

    safe_mdf = mdf_path.replace("'", "''")
    if ldf_path is not None:
        safe_ldf = ldf_path.replace("'", "''")
        sql = (
            f"CREATE DATABASE [{db_name}] "
            f"ON (FILENAME = N'{safe_mdf}'), (FILENAME = N'{safe_ldf}') "
            "FOR ATTACH"
        )
        print(f"Attaching '{mdf_path}' + '{ldf_path}' as database '{db_name}'...")
    else:
        sql = (
            f"CREATE DATABASE [{db_name}] "
            f"ON (FILENAME = N'{safe_mdf}') "
            "FOR ATTACH_REBUILD_LOG"
        )
        print(f"Attaching '{mdf_path}' as database '{db_name}' (rebuilding log)...")

    with pyodbc.connect(conn_str, autocommit=True) as conn:
        print("Connected to SQL Server successfully.")
        conn.execute(sql)
    print(f"Database '{db_name}' attached successfully.")


def restore_bak(bak_path: str, db_name: str) -> None:
    """Restore a BAK file to the local SQL Server instance."""
    sa_password = os.environ.get("SA_PASSWORD")
    if not sa_password:
        raise EnvironmentError("SA_PASSWORD environment variable is not set")

    # Validate inputs before embedding in DDL
    _validate_identifier(db_name, "DB_NAME")
    if not os.path.isabs(bak_path) or not bak_path.lower().endswith(".bak"):
        raise ValueError(f"Unexpected BAK path: {bak_path}")

    conn_str = _get_conn_str(sa_password)
    safe_path = bak_path.replace("'", "''")

    print(f"Restoring '{bak_path}' as database '{db_name}'...")
    with pyodbc.connect(conn_str, autocommit=True) as conn:
        print("Connected to SQL Server successfully.")

        # Discover the actual logical file names stored inside the backup
        cursor = conn.execute(f"RESTORE FILELISTONLY FROM DISK = N'{safe_path}'")
        columns = [col[0] for col in cursor.description]
        logical_data = None
        logical_log = None
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            file_type = row_dict.get("Type", "")
            if file_type == "D" and logical_data is None:
                logical_data = row_dict["LogicalName"]
            elif file_type == "L" and logical_log is None:
                logical_log = row_dict["LogicalName"]
        cursor.close()  # must close before issuing another command on this connection

        if not logical_data:
            raise ValueError("Could not find a data file (Type='D') in the backup file list")
        if not logical_log:
            raise ValueError("Could not find a log file (Type='L') in the backup file list")

        print(f"Backup logical names — data: '{logical_data}', log: '{logical_log}'")

        mdf_dest = os.path.join(MDF_DOWNLOAD_DIR, f"{db_name}.mdf")
        ldf_dest = os.path.join(MDF_DOWNLOAD_DIR, f"{db_name}_log.ldf")
        safe_mdf_dest = mdf_dest.replace("'", "''")
        safe_ldf_dest = ldf_dest.replace("'", "''")
        safe_logical_data = logical_data.replace("'", "''")
        safe_logical_log = logical_log.replace("'", "''")

        sql = (
            f"RESTORE DATABASE [{db_name}] "
            f"FROM DISK = N'{safe_path}' "
            f"WITH MOVE N'{safe_logical_data}' TO N'{safe_mdf_dest}', "
            f"MOVE N'{safe_logical_log}' TO N'{safe_ldf_dest}', "
            "REPLACE, RECOVERY"
        )
        conn.execute(sql)
    print(f"Database '{db_name}' restored successfully.")


def _send_task_success(task_token: str, db_name: str, s3_path: str) -> None:
    """Report successful completion back to Step Functions via task token."""
    sf_client = boto3.client("stepfunctions")
    sf_client.send_task_success(
        taskToken=task_token,
        output=json.dumps({
            "status": "SUCCESS",
            "dbName": db_name,
            "s3Path": s3_path,
        }),
    )
    print("Task success reported to Step Functions.")


def _send_task_failure(task_token: str, error: str, cause: str) -> None:
    """Report a failure back to Step Functions via task token."""
    sf_client = boto3.client("stepfunctions")
    sf_client.send_task_failure(
        taskToken=task_token,
        error=error,
        cause=cause,
    )
    print(f"Task failure reported to Step Functions: [{error}] {cause}")


def main():
    s3_path = os.environ.get("S3_PATH")
    if not s3_path:
        raise EnvironmentError("S3_PATH environment variable is not set")

    # Direct execution path — runs inside the ECS task container
    task_token = os.environ.get("TASK_TOKEN")

    db_name = os.environ.get("DB_NAME")
    if not db_name:
        filename = os.path.basename(urlparse(s3_path).path)
        db_name = os.path.splitext(filename)[0]
        print(f"DB_NAME not set, derived from filename: '{db_name}'")

    ldf_s3_path = os.environ.get("LDF_S3_PATH")

    ext = os.path.splitext(urlparse(s3_path).path)[1].lower()
    if ext not in (".mdf", ".bak"):
        raise ValueError(f"Unsupported file extension '{ext}'. Only .mdf and .bak are supported.")

    if ldf_s3_path and ext != ".mdf":
        raise ValueError("LDF_S3_PATH is only applicable when S3_PATH points to an .mdf file.")

    try:
        local_file = download_from_s3(s3_path)
        if ext == ".mdf":
            local_ldf = download_from_s3(ldf_s3_path) if ldf_s3_path else None
            attach_mdf(local_file, db_name, ldf_path=local_ldf)
        else:
            restore_bak(local_file, db_name)

        if task_token:
            _send_task_success(task_token, db_name, s3_path)

    except Exception as e:
        print(f"ERROR: {e}")
        if task_token:
            _send_task_failure(task_token, type(e).__name__, str(e))
        raise


if __name__ == "__main__":
    main()
