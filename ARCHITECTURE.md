# Mimari — SuperBI

## Backend (`/opt/superbi/app`)
- **main.py**: FastAPI entry
- **models/schemas.py**: Pydantic schemas
- **core/connector_registry.py**: DB connection (4 driver)
- **services/sql_builder.py**: Query builder + calculated field
- **services/expression_builder.py**: Formula validation (SBX + SQL)
- **services/sbx_compiler.py**: SBX → SQL derleyici (lark + sqlglot)
- **services/query_executor.py**: Query execute

## Frontend (`/opt/superbi/frontend`)
- Vanilla HTML/CSS/JS
- ECharts visualization

## Veritabanı
- SQLite: `/opt/superbi/data/superbi.db` (metadata)
- Oracle XE, MSSQL, MySQL, PostgreSQL: Data sources

## Key Technologies
- sqlglot==25.34.1 (pinned, AST + dialect translation)
- lark (LALR parser for SBX grammar)
- SQLAlchemy ORM
- Fernet (password encryption)
