FROM mcr.microsoft.com/mssql/server:2025-latest

ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y \
    MSSQL_PID=Express \
    SA_PASSWORD=YourStrong!Passw0rd \
    MSSQL_DATA_DIR=/var/opt/mssql/data \
    MSSQL_LOG_DIR=/var/opt/mssql/log \
    MSSQL_BACKUP_DIR=/var/opt/mssql/backup \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Ensure we're running as root for package installations
USER root

# Install Python, ODBC support, and the SQL Server ODBC driver needed by pyodbc.
RUN rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        ca-certificates \
        python3 \
        python3-pip \
        python3-dev \
        unixodbc-dev \
        locales \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/microsoft.gpg \
    && curl https://packages.microsoft.com/config/ubuntu/24.04/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18 \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen en_US.UTF-8

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PATH="/opt/mssql-tools18/bin:${PATH}"

RUN mkdir -p /var/opt/mssql/data /var/opt/mssql/log /var/opt/mssql/backup /app

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

COPY main.py /app/main.py

EXPOSE 1433

CMD ["/opt/mssql/bin/sqlservr"]
