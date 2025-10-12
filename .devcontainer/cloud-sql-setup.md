# Cloud SQL Auth Proxy & PostgreSQL Dev Setup

This guide explains how to connect your development environment (including GitHub Codespaces) to a Google Cloud SQL PostgreSQL database using the Cloud SQL Auth Proxy, Google Secret Manager, and supervisord.

---

## Prerequisites

- Access to the Google Cloud project and Cloud SQL instance
- The following secrets set up in Google Secret Manager:
  - **Instance connection name**
- Your dev environment has:
  - Python 3, pip, Node.js, npm, and Git (pre-installed in this dev container)
  - Google Cloud CLI (`gcloud`)
  - Cloud SQL Auth Proxy (installed automatically by the dev container setup)
  - supervisord

---

## 1. Authenticate with Google Cloud

Open a terminal in your Codespace or dev container and run:

```sh
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project <PROJECT_ID>
```

---

## 2. Ensure Cloud SQL Auth Proxy is Installed

The dev container setup script will install the proxy automatically. If you need to install it manually:

```sh
sudo curl -o /usr/local/bin/cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.10.1/cloud-sql-proxy.linux.amd64
sudo chmod +x /usr/local/bin/cloud-sql-proxy
```

---

## 3. Fetch the Instance Connection Name from Secret Manager

The dev container uses a wrapper script:  
`.devcontainer/start-cloud-sql-proxy.sh`

This script fetches the instance connection name from Secret Manager and starts the proxy.

**Example secret fetch command:**

```sh
gcloud secrets versions access latest --secret="YOUR_SECRET_NAME" --project="PROJECT_ID"
```

---

## 4. Start the Cloud SQL Auth Proxy

You can start the proxy in two ways:

### a) Using supervisord (recommended)

```sh
supervisord -c /workspaces/durham-environmental-monitoring/.devcontainer/supervisord.conf
```

Check status:

```sh
supervisorctl -c /workspaces/durham-environmental-monitoring/.devcontainer/supervisord.conf status
```

Restart the proxy if needed:

```sh
supervisorctl -c /workspaces/durham-environmental-monitoring/.devcontainer/supervisord.conf restart cloud-sql-proxy
```

### b) Run the wrapper script directly

```sh
.devcontainer/start-cloud-sql-proxy.sh
```

---

## 5. Connect to PostgreSQL

Use the following connection parameters in your application or database client:

- **Host:** `127.0.0.1`
- **Port:** `5432`
- **User:** (as configured, e.g., `postgres`)
- **Password:** (as configured)
- **Database:** (as configured, e.g., `postgres`)

---

## 6. Troubleshooting

- **Proxy not running?**  
  Check logs:  
  `/tmp/cloud-sql-proxy.err.log`  
  `/tmp/cloud-sql-proxy.out.log`

- **Permission denied for proxy binary?**  
  Run:  
  `sudo chmod +x /usr/local/bin/cloud-sql-proxy`

- **gcloud authentication errors?**  
  Make sure you have run both `gcloud auth login` and `gcloud auth application-default login`.

- **Supervisorctl errors?**  
  Make sure supervisord is running and your config includes `[unix_http_server]`, `[supervisord]`, `[rpcinterface:supervisor]`, and `[supervisorctl]` sections.

---

## References

- [Cloud SQL Auth Proxy Documentation](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy)
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs)
- [supervisord Documentation](http://supervisord.org/)

---

**Happy coding!**
