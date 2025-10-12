# [Deprecated] Cloud SQL Auth Proxy & PostgreSQL Dev Setup

**This guide is deprecated.**

The project has migrated to a BigQuery-only pipeline. Cloud SQL/PostgreSQL is no longer required for development or production. All instructions for Cloud SQL, PostgreSQL, and the Cloud SQL Auth Proxy can be ignored and removed from your local setup.

For all data ingestion, transformation, and analytics, use BigQuery as described in the main README and scripts.
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
