# PostgreSQL initial data

`001-luxstudio.sql.gz` is a local PostgreSQL-native snapshot used only when
Docker creates a brand-new `postgres_data` volume. It is intentionally ignored
by Git because it contains application data. The persistent Docker volume is
the primary database after initialization.
