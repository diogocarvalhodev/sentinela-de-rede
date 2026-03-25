# NVR Monitor

![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-Integrated-E6522C?logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800?logo=grafana&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-State%20Storage-003B57?logo=sqlite&logoColor=white)
![Profiles](https://img.shields.io/badge/Profiles-Education%20%7C%20Retail%20%7C%20Industrial-6A5ACD)

Monitoramento de endpoints de rede com descoberta automatica de IPs, metricas em tempo real e dashboards prontos para operacao.

## Destaques
1. Ciclo inteligente de discovery: incremental + fallback full scan.
2. Persistencia operacional local em SQLite.
3. Telemetria em Prometheus e visualizacao em Grafana.
4. Reuso por nicho com o mesmo design de dashboard, mudando apenas textos.
5. Projeto pronto para demonstracao publica com dados anonimizados.

## Demo Stack
Arquitetura de runtime:
1. Exporter Python (coleta e processamento)
2. Prometheus (series temporais)
3. Grafana (visualizacao)

## Quickstart
1. Ajuste o arquivo units.json para o seu ambiente.
2. Suba os servicos:

```bash
docker compose up -d --build
```

3. Acesse:
1. Exporter: http://localhost:8000/metrics
2. Prometheus: http://localhost:9090
3. Grafana: http://localhost:3001

4. Credenciais do Grafana:
1. Usuario: admin
2. Senha: admin

Para parar:

```bash
docker compose down
```

## Perfis de Nicho
Dashboards prontos, com visual consistente:
1. Educacao: dashboards/nvr-dashboard.json
2. Varejo: dashboards/nvr-dashboard-retail.json
3. Industrial: dashboards/nvr-dashboard-industrial.json

Regenerar dashboards de perfil:

```powershell
./scripts/generate_dashboard_profiles.ps1
```

## Estrutura do Projeto
1. exporter.py
2. nvr_monitor/
3. dashboards/
4. config/
5. profiles/
6. examples/
7. data/

## Dados e Privacidade
1. Estado operacional em data/monitor.db.
2. units.json usado somente para bootstrap inicial quando o banco estiver vazio.
3. Nomes de unidades anonimizados para apresentacao publica.
