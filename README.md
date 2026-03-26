# Sentinela de Rede

Sistema de monitoramento de endpoints de rede com descoberta automática de ativos, coleta de métricas em tempo real e visualização operacional através de dashboards.

Projetado para simular ambientes de missão crítica com foco em observabilidade, automação e resposta rápida a incidentes.

---

## 🚀 Principais Capacidades

* Descoberta automática de dispositivos na rede (IP scanning inteligente)
* Coleta contínua de métricas operacionais
* Persistência de estado para evitar reprocessamento desnecessário
* Visualização em tempo real com dashboards prontos
* Estrutura reutilizável para múltiplos cenários (educacional, varejo, industrial)

---

## 🧠 Arquitetura da Solução

A aplicação segue uma arquitetura baseada em observabilidade e coleta contínua:

* **Exporter em Python** responsável pela descoberta de rede e exposição de métricas
* **Prometheus** para coleta e armazenamento de métricas em séries temporais
* **Grafana** para visualização e análise operacional
* **SQLite** para persistência local do estado da aplicação

Fluxo:

1. O sistema realiza descoberta de IPs na rede
2. Dispositivos ativos são monitorados continuamente
3. Métricas são expostas via endpoint `/metrics`
4. Prometheus coleta os dados
5. Grafana exibe dashboards operacionais em tempo real

---

## ⚙️ Tecnologias Utilizadas

* Python
* Prometheus
* Grafana
* Docker / Docker Compose
* SQLite

---

## 🔍 Diferenciais Técnicos

* **Ciclo de discovery inteligente:** combinação de varredura incremental com fallback para full scan
* **Persistência de estado:** evita redundância e melhora performance
* **Design multi-nicho:** reutilização da mesma arquitetura para diferentes contextos operacionais
* **Projeto orientado a demonstração real:** dados anonimizados e prontos para apresentação

---

## 📊 Observabilidade

* Métricas expostas no padrão Prometheus
* Dashboards prontos no Grafana
* Monitoramento contínuo de disponibilidade de endpoints

---

## 🐳 Como Executar

### Pré-requisitos

* Docker
* Docker Compose

### Subir o ambiente

```bash
docker compose up -d --build
```

### Acessos

* Exporter: http://localhost:8000/metrics
* Prometheus: http://localhost:9090
* Grafana: http://localhost:3001

### Credenciais Grafana

* Usuário: admin
* Senha: admin

### Parar o ambiente

```bash
docker compose down
```

---

## 🧩 Perfis de Uso

Dashboards adaptados para diferentes cenários:

* Educação
* Varejo
* Industrial

Regenerar dashboards:

```bash
./scripts/generate_dashboard_profiles.ps1
```

---

## 📁 Estrutura do Projeto

* `exporter.py` — coleta e exposição de métricas
* `nvr_monitor/` — lógica de monitoramento
* `dashboards/` — dashboards Grafana
* `config/` — configurações
* `profiles/` — perfis por nicho
* `data/` — persistência local

---

## 🔐 Dados e Privacidade

* Persistência local em SQLite (`data/monitor.db`)
* Dados anonimizados para uso público
* `units.json` utilizado apenas para bootstrap inicial

---

## 📈 Possíveis Evoluções

* Integração com mensageria (RabbitMQ/Kafka)
* Alertas automatizados (Telegram, Slack)
* Deploy em ambiente cloud
* Pipeline de CI/CD
* Escalabilidade horizontal

---

## 👨‍💻 Autor

Diogo Carvalho
Software Engineer | Backend Python | SRE / DevOps | Distributed Systems
