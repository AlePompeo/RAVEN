<!-- SPDX-License-Identifier: Apache-2.0 -->
# 🌑 RAVEN — Lunar Landing Site Navigator
### *Rapid Assessment & Visual Exploration of Lunar Navigation*

[![NASA Space Apps Challenge 2026](https://img.shields.io/badge/NASA%20Space%20Apps-2026%20Challenge-0B3D91?style=for-the-badge&logo=nasa&logoColor=white)](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![Frontend: Svelte 5 + Vite](https://img.shields.io/badge/Frontend-Svelte%205%20%2B%20Vite%20%2B%20TS-FF3E00?style=for-the-badge&logo=svelte&logoColor=white)](frontend/)
[![3D Engine: Three.js + 2D Canvas](https://img.shields.io/badge/3D%20Engine-Three.js%20%2B%20Canvas2D%20Fallback-000000?style=for-the-badge&logo=threedotjs&logoColor=white)](frontend/src/viewports/)
[![Offline AI: Zero Cloud Token](https://img.shields.io/badge/Offline%20AI-Zero%20Token%20%2F%20100%25%20Local-2E7D32?style=for-the-badge&logo=ollama&logoColor=white)](backend/assistant/)
[![Accessibility: WCAG 2.2 AA](https://img.shields.io/badge/Accessibility-WCAG%202.2%20AA%20Verified-4CAF50?style=for-the-badge)](e2e/tests/a11y.spec.ts)
[![Docker Ready](https://img.shields.io/badge/Deployment-Docker%20Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](compose.yaml)

---

## 🌟 Executive Overview & Hackathon Challenge

**RAVEN (Rapid Assessment & Visual Exploration of Lunar Navigation)** is a high-fidelity, intuitive mission planning and scientific decision-support web platform engineered for the **NASA Space Apps Challenge 2026** under the challenge:

> **[Lunar Landing Site Navigator](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/)**  
> *Event:* 2026 NASA Space Apps Challenge · *Difficulty:* Advanced / Intermediate  
> *Subjects:* Human Exploration, Moon, Software, Space Exploration

### 🎯 The Challenge: The South Pole Conundrum

The Moon’s South Pole has emerged as the frontier of human and robotic exploration (NASA Artemis, Commercial Lunar Payload Services — CLPS, ESA, and international initiatives) due to its reservoirs of volatile water ice hidden in **Permanently Shadowed Regions (PSRs)**. However, operating at the lunar south pole presents extreme physical and operational bottlenecks:

1. **Grazing Solar Dynamics:** The solar elevation angle oscillates merely between approximately $-1.5^\circ$ and $+1.5^\circ$ relative to the mean sphere. Crater rims, massifs, and ridges cast colossal, rapidly moving dynamic shadows across potential landing zones. A difference of a few meters in landing location or a few hours in departure date can mean the difference between abundant solar power and catastrophic freezing darkness.
2. **Direct-to-Earth (DTE) Horizon Blockage:** Because the Earth also hovers at a very low elevation ($\sim 1^\circ$ above the horizon), topographical elevations create knife-edge obstacles. Pure line-of-sight geometric visibility is insufficient: electromagnetic waves experience **diffraction, terrain grazing losses, and multipath degradation**.
3. **The Agile Planning Gap:** Current reference tools — such as *NASA QuickMap*, *Moon Trek*, and the *JPL Horizons System* — provide rich technical datasets but are fragmented across separate interfaces with steep learning curves. Mission timelines regularly face delays or contingency recalculations; engineers, planners, and educators need to evaluate alternatives (e.g. *Shackleton Crater* vs. *Malapert Massif* vs. *Haworth*) instantaneously without weeks of manual cross-referencing.

**RAVEN bridges this gap:** An intuitive, unified, publication-grade web application translating complex ephemeris and LOLA topographic data into clear, comparable visualizations, quantitative link margins, and automated mission feasibility verdicts.

---

## 🏛️ System Architecture

RAVEN is designed as a **Modular Hexagonal Monolith (*Ports & Adapters*)**. The architecture enforces zero coupling between the pure domain physics and external infrastructure, ensuring that any component can operate locally, in an isolated container, or as an independent service without altering core logic.

```mermaid
flowchart TB
    subgraph Client["🖥️ Universal Frontend (Svelte 5 + Vite + TypeScript)"]
        UI["Mission Planner & Scenario Comparison"]
        VP["ViewportPort: Three.js WebGL (3D) + Pure Canvas 2D (Fallback)"]
        Chat["RAVEN SI Conversational Interface"]
        PDF["Executive PDF Dossier Exporter"]
    end

    subgraph CorePlatform["🛰️ RAVEN Hexagonal Core (FastAPI + Python 3.12+)"]
        API["REST Endpoints & Server-Sent Events (SSE)"]
        Contracts["JSON-Schema Single Source of Truth (Pydantic / TS Generated)"]
        
        subgraph Engine["⚙️ RAVEN Engine (8-Stage Physical Pipeline)"]
            S0["S0: Epoch & IAU Feature / Coordinate Selection"]
            S1["S1: NAIF / JPL DE440 Ephemeris Vectors"]
            S2["S2: LOLA DEM Topographic 360° Ray-Tracing"]
            S3["S3: Solar Disk Horizon & Optical Illumination"]
            S4["S4: Photovoltaic Flux & Battery SoC Energy Model"]
            S5["S5: Direct-to-Earth Link Margin & Knife-Edge Diffraction"]
            S6["S6: Deep Space Network (DSN) Ground Line-of-Sight"]
            S7["S7: Pareto Optimization, Usable Hours & Site Ranking"]
        end

        subgraph SI["🧠 RAVEN SI (Synthetic Intelligence)"]
            LocalLLM["llama.cpp Engine (IBM Granite 350M / 1B Q4_K_M)"]
            RAG["BM25F Citation-Grounded Knowledge RAG"]
            Intent["Natural Language Mission Intent Parser"]
            Verdict["Autonomous Report Verdict Synthesizer"]
        end

        subgraph Prediction["📈 RAVEN Prediction Model (ML / Estimators)"]
            ONNX["ONNX Neural Fast Surrogate Predictors"]
            Fusion["Sensor Fusion: EKF & Madgwick AHRS (imufusion)"]
            Gate["Human-Gated Model Verification Gate"]
        end
    end

    subgraph DataSources["📡 High-Fidelity Planetary Data Sources"]
        JPL["NASA JPL DE440 Ephemerides"]
        LOLA["NASA PDS Lunar Orbiter Laser Altimeter (LOLA DEM)"]
        DSN_SPEC["NASA DSN 810-005 Telecommunication Spec"]
        ITU["ITU-R P.526-9 Radio Diffraction Standard"]
    end

    Client <-->|HTTP / REST & SSE Stream| API
    API --> Contracts
    Contracts --> Engine
    Engine --> DataSources
    Engine <--> SI
    Engine <--> Prediction
```

---

## 🔬 Core Architectural Pillars

### 1. 🌑 RAVEN (The Core Platform & Experience)
* **Modular Monolith & Strict Boundary Enforcement:** Guided by `import-linter` with four verified contracts: `backend.core` never imports from API, adapters, ML, or network layers.
* **Dual-Experience Modes:**
  * **Learning Mode (Default):** Plain-language scientific narrative, visual cues, accessible explanations for students, enthusiasts, and educators.
  * **Advanced Mode:** Unfiltered engineering telemetry, link budget breakdowns ($E_b/N_0$, EIRP, $G/T$, free space path loss), raw parameter tables, and CSV/JSON exports.
* **Universal Rendering Engine (`ViewportPort`):** Combines an ultra-smooth **Three.js** 3D WebGL simulator with a **100% Canvas 2D fallback**. The platform runs identically on high-end workstations, smartphones, low-power laptops, and Smart TVs without WebGL support.
* **Hermetic & Accessible:** Built to strictly adhere to **WCAG 2.2 AA**, complete keyboard navigation, D-pad TV mode, and zero non-essential cookies.

### 2. ⚙️ RAVEN Engine (Celestial & Physics Computing Engine)
The mathematical backbone of RAVEN executes an uncompromised 8-stage physical pipeline:
* **Stage S0 — Geometry & Site Setup:** Precise lunar IAU coordinates covering 51 pre-computed polar landing sites, plus dynamic ingestion of arbitrary custom coordinates.
* **Stage S1 — Ephemerides:** Milliradian-accurate positioning of the Sun, Earth, and Moon using NASA NAIF / JPL DE440 kernels, including Earth's libration oscillations.
* **Stage S2 — Topography & Horizons:** 360-degree local horizon azimuth-elevation profiles computed directly from high-resolution NASA Lunar Orbiter Laser Altimeter (**LOLA DEM**) datasets (20 m to 240 m resolution).
* **Stage S3 — Solar Illumination:** Optical ray-tracing accounting for the finite solar angular diameter ($0.5^\circ$), partial disc eclipse by local terrain, and grazing incidence angles.
* **Stage S4 — Power & Energy Balance:** Solar array generation coupled with thermal limitations, operational power baselines, and a continuous battery State-of-Charge (SoC) model.
* **Stage S5 — RF Link Budget & Grazing Diffraction:** Direct-to-Earth telecommunications modeling combining Friis Free Space Path Loss (FSPL) with **ITU-R P.526-9 knife-edge and rounded-ridge obstacle diffraction**. Accounts for antenna gains, receiver figure of merit ($G/T$), and required link margins.
* **Stage S6 — Deep Space Network (DSN) Visibility:** Geometric tracking from Earth ground complexes (Goldstone, Madrid, Canberra) above standard $6^\circ$ elevation operational masks.
* **Stage S7 — Operational Synthesis:** Algorithmic calculation of continuous operational mission windows, uninterrupted useful hours, and multi-criteria site ranking.

### 3. 🧠 RAVEN SI (Synthetic Intelligence & Local Learning Assistant)
* **100% Offline & Zero-Token Cost:** Driven by `llama.cpp` hosting optimized quantized Small Language Models (SLMs) such as **IBM Granite 350M / 1B Q4_K_M** directly on `127.0.0.1`. No external API keys or cloud tokens are required, and no private mission data leaves the host.
* **Lazy Daemon Management:** Automatically started on demand and unloads from system RAM after 5 minutes of inactivity, keeping steady-state memory below 2–3 GB.
* **BM25F Citation-Grounded RAG:** Answers queries by grounding responses strictly in verified repository scientific documentation. Every answer provides traceable references, eliminating LLM hallucinations.
* **Natural Language Intent Extraction:** Allows planners to input mission profiles in natural language (e.g. *"I need a site with at least 100 continuous hours of Earth communication between March and May 2027"*), which RAVEN SI translates into active filter parameters.
* **Automated Executive PDF Verdict:** Automatically drafts a comparative scientific conclusion included at the end of the downloadable mission PDF dossier.

### 4. 📈 RAVEN Prediction Model (ML & Fast Surrogate Layer)
* **Fast Neural Surrogate Estimators:** Employs ONNX Runtime models to approximate heavy topographic horizon ray-tracing, enabling real-time sweeping of entire candidate regions in milliseconds.
* **Sensor Fusion & Attitude Estimation:** Integrates Extended Kalman Filtering (EKF) and Madgwick AHRS estimators (via `imufusion`) to model lander orientation and directional antenna gimbal tracking.
* **Multi-Objective Pareto Frontiers:** Computes optimal trade-offs between conflicting mission requirements (e.g. maximizing solar power vs. maximizing Earth contact time).
* **Safe ML Governance:** Incorporates human-in-the-loop promotion gates; models cannot alter active production logic without Passing explicit validation test suites.

---

## 📊 Feature Comparison Matrix

| Capability | Existing Reference Tools (QuickMap, Horizons) | RAVEN Lunar Navigator |
|---|---|---|
| **Scenario Comparison** | Sequential lookup across multiple tools | Instant side-by-side comparative views & Pareto trade-offs |
| **RF Grazing & Diffraction** | Basic line-of-sight only (binary visible/hidden) | ITU-R P.526-9 knife-edge diffraction & link margin calculation |
| **Integrated Power & Comms** | Disconnected datasets | Fully coupled solar flux, battery SoC, and DTE communication |
| **Offline Deployment** | Cloud/Web only | 100% self-contained local installation with offline LLM |
| **User Interface** | Expert GIS interface | Dual-Mode: Cinematic Apple/NASA-Eyes style + Advanced Engineering |
| **Hardware Accessibility** | Heavy GPU/WebGL requirements | WebGL 3D + 100% pure Canvas 2D fallback for any device |
| **Mission Dossier Output** | Manual screenshots and data collation | Automated vector PDF report with formulas and AI verdict |

---

## 🗺️ Future Roadmap & Scientific Vision

```mermaid
timeline
    title RAVEN Strategic Development Roadmap
    Phase 1 (Completed) : NASA Space Apps Core : 8-Stage Physical Engine : 51 Polar Sites + Custom Coordinates : Local Offline SLM (RAVEN SI) : PDF Dossier Generator
    Phase 2 (Near-Term) : Multi-Hop Orbital Relays : LunaNet & ESA Moonlight Integration : Expanded DEM Raytracing to 75°S : Sub-meter Microtopography
    Phase 3 (Mid-Term) : Autonomous Traverse Planner : Slope Hazard Analysis for Mobile Rovers : Continuous RF & Sun Tethering : Dynamic Thermal Radiator Model
    Phase 4 (Long-Term) : CCSDS Space Packet Ingestion : Hardware-in-the-Loop (HIL) Flight Model Coupling : Distributed Swarm Mission Coordination
```

* **Phase 1 — Core Baseline (Current Release):**
  - Complete 8-stage physical pipeline with verified astronomical ephemerides (JPL DE440) and LOLA topography.
  - Interactive Svelte 5 frontend with WebGL/Canvas2D dual renderers.
  - Local offline Synthetic Intelligence (`llama.cpp` + Granite SLM) and automated PDF reporting.
* **Phase 2 — Multi-Hop Relays & Lunar Constellations:**
  - Support for orbital communication relays (**LunaNet** architecture and **ESA Moonlight** constellation) when direct-to-Earth line of sight is obstructed.
  - Sub-meter microtopographic hazard ingestion for landing precision.
* **Phase 3 — Autonomous Rover Traverse Navigation:**
  - Dynamic pathfinding for mobile surface exploration vehicles traversing from sunlit ridges into Permanently Shadowed Regions (PSRs).
  - Multi-variable cost-function optimization combining slope slip risk, solar recharge windows, and RF tethering.
* **Phase 4 — Flight Hardware In-The-Loop (HIL) & Real Telemetry:**
  - Native integration with CCSDS space telecommand and telemetry packet streams.
  - Embedded micro-controller simulation (FreeRTOS / ESP32 HAL) for testing lander guidance, navigation, and control (GNC).

---

## 💰 Economic Viability & Environmental Sustainability

* **Zero Cloud Expenditure ($0/mo SaaS Footprint):** By architecting RAVEN with lightweight, quantized local models (Granite 350M/1B) and an in-process FastAPI engine, the platform requires no recurring cloud API subscriptions, no external token billing, and no costly remote server clusters.
* **Green Computing & Low-Power Hardware:** Designed to run comfortably on standard commercial off-the-shelf (COTS) consumer laptops and edge devices with $\le 4$ CPU cores and $\le 4$ GB of available RAM. Automatic process unloading ensures zero passive energy waste.
* **Mission De-risking for CLPS & Explorers:** Pre-Phase A and Phase A lunar mission design cycles typically cost hundreds of thousands of dollars in engineering person-hours. RAVEN compresses site feasibility trade-offs from weeks into minutes, providing immediate scientific feedback and preventing costly late-stage mission redesigns.

---

## 👥 Project Team & Contacts

*This project was developed for the NASA Space Apps Challenge 2026. For detailed contact information, team credentials, and clickable LinkedIn profiles, visit the in-app **Contacts** view (`/contacts`).*

<div align="center">

| Contributor | Focus Area | Role & Background | Links |
|:---:|:---:|:---:|:---:|
| **Alessio Pompeo** | *Electronics, Telecommunications & Power* | RF Link Budget, Topographic Diffraction, Power & Battery Modeling, System Verification | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white)](https://linkedin.com) [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/AlePompeo) |
| **Team Collaborator** | *Informatics, AI & Space Robotics* | Ephemeris Integration, Backend & Frontend Architecture, 3D Rendering, Machine Learning | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white)](https://linkedin.com) [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com) |

</div>

---

## 🚀 Quickstart & Installation

### Option 1: Automated Local Installation (Recommended)
RAVEN includes a self-contained installation script that inspects prerequisites, sets up virtual environments, downloads verified ephemerides and LOLA DEM tiles in parallel, and starts the platform:

```bash
# Clone the repository
git clone https://github.com/AlePompeo/RAVEN.git
cd RAVEN

# Run the automated installer (no root or sudo required)
./install.sh
```

*Options for `./install.sh`:*
* `--yes`: Non-interactive mode (accepts default downloads).
* `--no-browser`: Do not auto-launch default web browser.
* `--port <PORT>`: Bind to a specific HTTP port (default: `8000`).
* `--with-llm`: Download and configure local offline LLM (`llama.cpp` + Granite SLM).

To stop the background server:
```bash
./stop.sh
```

### Option 2: Docker Container
Run the entire platform inside an isolated container:

```bash
docker compose up --build
```
Then navigate to `http://127.0.0.1:8000` in your web browser.

---

## 🧪 Verification & Development

RAVEN enforces strict engineering rigor with comprehensive automated test suites:

```bash
# Backend pytest suite (over 1500 unit and integration tests)
make test

# Type checking and strict linting (Ruff, Mypy, Import-Linter)
make lint

# Frontend component tests (Vitest: 95 test suites, 1050+ tests)
cd frontend && npm test

# Frontend type verification
cd frontend && npm run check

# Production bundle compilation
cd frontend && npm run build
```

---

## 📜 Scientific References & Acknowledgments

* **Planetary Ephemerides:** NASA NAIF / JPL DE440 Solar System Planetary Ephemeris.
* **Topography Data:** NASA Planetary Data System (PDS) Lunar Reconnaissance Orbiter (LRO) Lunar Orbiter Laser Altimeter (LOLA) Science Team.
* **Diffraction Standards:** International Telecommunication Union (ITU-R) Recommendation P.526-9 *"Propagation by diffraction"*.
* **Ground Stations:** NASA Deep Space Network (DSN) Telecommunications Link Design Handbook (810-005).
* **Star Mapping:** NASA Scientific Visualization Studio (SVS) Deep Star Maps 2020.
* **Visual Imagery:** NASA Apollo 8 AS08-14-2383 *"Earthrise"*.

---

<div align="center">
  <sub>Engineered with precision for the NASA Space Apps Challenge 2026. Distributed under the Apache-2.0 License.</sub>
</div>
