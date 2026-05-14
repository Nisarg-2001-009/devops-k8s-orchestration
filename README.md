# devops-k8s-orchestration

A production-grade Kubernetes project demonstrating the core patterns every DevOps engineer needs to know: zero-downtime rolling updates, automatic self-healing, horizontal pod autoscaling, health-probe-driven traffic management, and clean separation of configuration from code. Two Python microservices are containerised, published to Docker Hub, and orchestrated across a full Kubernetes stack — Namespace, ConfigMap, Secret, Deployments, Services, Ingress, and an HPA — all with detailed, educational manifests designed to be read alongside the code.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Kubernetes Concepts](#kubernetes-concepts)
3. [Tech Stack](#tech-stack)
4. [Prerequisites](#prerequisites)
5. [Project Structure](#project-structure)
6. [Setup Instructions](#setup-instructions)
7. [kubectl Command Reference](#kubectl-command-reference)
8. [Key Demonstrations](#key-demonstrations)
   - [Rolling Update](#1-rolling-update)
   - [Self-Healing](#2-self-healing)
   - [Horizontal Pod Autoscaling](#3-horizontal-pod-autoscaling)
9. [Health Probes](#health-probes)
10. [Docker Hub Images](#docker-hub-images)
11. [Lessons Learned](#lessons-learned)

---

## Architecture

The diagram below shows every Kubernetes object in this project and how traffic flows through the cluster from an external browser request down to an individual container.

```
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                          Kubernetes Cluster                               │
  │                                                                            │
  │  ┌──────────────────────────────────────────────────────────────────┐    │
  │  │                    Namespace: microservices                        │    │
  │  │                                                                    │    │
  │  │   ╔══════════════════════════════════════════════════════╗        │    │
  │  │   ║           Ingress: microservices-ingress              ║        │    │
  │  │   ║   host: microservices.local                           ║        │    │
  │  │   ║   /api  ──►  api-service:80                           ║        │    │
  │  │   ║   /     ──►  api-service:80  (catch-all)              ║        │    │
  │  │   ╚═══════════════════════╦══════════════════════════════╝        │    │
  │  │                           │                                         │    │
  │  │   ┌───────────────────────▼──────────────────────────────┐        │    │
  │  │   │          Service: api-service  (ClusterIP)            │        │    │
  │  │   │          port 80  ──►  targetPort 8080                │        │    │
  │  │   └──────────┬────────────────┬───────────────┬──────────┘        │    │
  │  │              │                │               │                     │    │
  │  │   ┌──────────▼──────┐ ┌──────▼──────┐ ┌─────▼───────┐           │    │
  │  │   │   api Pod 1      │ │  api Pod 2   │ │  api Pod N  │           │    │
  │  │   │   :8080          │ │  :8080       │ │  :8080      │           │    │
  │  │   │   v2.0.0         │ │  v2.0.0      │ │  v2.0.0     │           │    │
  │  │   └─────────────────┘ └─────────────┘ └─────────────┘           │    │
  │  │        ▲   HPA: api-service-hpa  min=2  max=10  CPU target=50%   │    │
  │  │        └──────────────────────────────────────────────────────    │    │
  │  │                           │                                         │    │
  │  │                    calls  │  http://worker-service:8080             │    │
  │  │                           │  (in-cluster DNS)                       │    │
  │  │   ┌───────────────────────▼──────────────────────────────┐        │    │
  │  │   │        Service: worker-service  (ClusterIP)           │        │    │
  │  │   │        port 8080  ──►  targetPort 8080                │        │    │
  │  │   └───────────────────┬─────────────────┬────────────────┘        │    │
  │  │                       │                 │                           │    │
  │  │   ┌───────────────────▼────┐ ┌──────────▼──────────────┐         │    │
  │  │   │   worker Pod 1          │ │   worker Pod 2            │         │    │
  │  │   │   :8080  v1.0.0        │ │   :8080  v1.0.0           │         │    │
  │  │   └────────────────────────┘ └──────────────────────────┘         │    │
  │  │                                                                    │    │
  │  │   ┌─────────────────────────┐   ┌───────────────────────┐        │    │
  │  │   │  ConfigMap: app-config  │   │  Secret: app-secret    │        │    │
  │  │   │  APP_ENV=production     │   │  API_KEY=***           │        │    │
  │  │   │  LOG_LEVEL=info         │   │  (base64-encoded)      │        │    │
  │  │   │  WORKER_SERVICE_URL=... │   └───────────────────────┘        │    │
  │  │   └─────────────────────────┘                                      │    │
  │  │        Both injected via envFrom into every Pod                    │    │
  │  └──────────────────────────────────────────────────────────────────┘    │
  │                                                                            │
  │   Metrics Server  ──►  HPA controller  ──►  api-service Deployment       │
  │   (collects CPU)        (scales replicas)     (adjusts replica count)     │
  └──────────────────────────────────────────────────────────────────────────┘

  External User
  ──────────────►  NGINX Ingress Controller  ──►  microservices.local/*
  (browser/curl)   (NodePort / LoadBalancer)
```

**Traffic flow in plain English:**

1. A browser sends `GET http://microservices.local/api/info`.
2. The NGINX Ingress Controller receives it (it's watching all Ingress resources in the cluster).
3. The Ingress rule matches `host: microservices.local` and `path: /api`, and forwards the request to the `api-service` Service on port 80.
4. The Service's kube-proxy rules load-balance the request across the healthy api-service Pods.
5. The selected Pod handles the request and — for the `/api/process` route — calls `http://worker-service:8080` using Kubernetes in-cluster DNS.
6. The worker-service Service load-balances that call across its two Pods, which process the work and respond.

---

## Kubernetes Concepts

| Object | What it is | What it does in this project |
|--------|-----------|------------------------------|
| **Namespace** | A virtual cluster inside the real cluster. Resources inside a Namespace are isolated by name from all other Namespaces. | All resources live in `microservices`, preventing name collisions with anything in `default` and making teardown as simple as `kubectl delete namespace microservices`. |
| **Pod** | The smallest deployable unit in Kubernetes. One or more containers that share a network interface and storage. Pods are ephemeral — they get a new IP when recreated. | Each api-service and worker-service instance runs as a Pod. We never manage Pods directly; Deployments do it for us. |
| **Deployment** | A controller that declares "I want N copies of this Pod template running at all times." It owns a ReplicaSet which creates and replaces Pods. | `api-deployment.yaml` keeps 3 api-service Pods running (overridden at runtime by the HPA). `worker-deployment.yaml` keeps 2 worker-service Pods running. Both use rolling-update strategy for zero-downtime releases. |
| **Service** | A stable virtual IP and DNS name that load-balances traffic across the Pods matching its selector. Abstracts away the fact that Pod IPs change. | `api-service` (port 80→8080) is the target for the Ingress. `worker-service` (port 8080→8080) is used by api-service for in-cluster calls. Both are `ClusterIP` — not reachable externally without the Ingress. |
| **Ingress** | A layer-7 HTTP routing rule. By itself it is just configuration; an Ingress Controller (NGINX here) reads it and reconfigures its reverse proxy. | Routes `microservices.local/api/*` and `microservices.local/` to the api-service. worker-service is intentionally hidden from external traffic. |
| **ConfigMap** | Key-value store for non-sensitive configuration. Values are plain text and visible to anyone with `kubectl get configmap`. | Injects `APP_ENV`, `LOG_LEVEL`, and `WORKER_SERVICE_URL` as environment variables into every Pod via `envFrom`. Changing a value and rolling the Deployment is the correct way to push config changes without rebuilding the image. |
| **Secret** | Key-value store for sensitive data. Values are base64-encoded (not encrypted by default, but separately RBAC-gated and eligible for KMS encryption-at-rest). | Injects `API_KEY` into every Pod. The file in this repo contains a placeholder — in production, a secret manager (Vault, AWS Secrets Manager, External Secrets Operator) would inject the real value at deploy time. |
| **HPA** | HorizontalPodAutoscaler. A controller that watches a metric (here: CPU utilisation) and adjusts a Deployment's `replicas` field up or down to hit a target. | `api-service-hpa` keeps average CPU at 50% of each Pod's request (100 m), scaling between 2 and 10 replicas. worker-service is scaled statically because its traffic is proportional to api-service and does not benefit from independent autoscaling. |

---

## Tech Stack

| Layer | Technology | Version | Role |
|-------|-----------|---------|------|
| **Runtime** | Python | 3.11 | Application language for both microservices |
| **Web framework** | Flask | 3.x | HTTP server and routing |
| **WSGI server** | Gunicorn | 21.x | Production-grade process manager for Flask |
| **Container runtime** | Docker | 24+ | Build and run container images |
| **Container registry** | Docker Hub | — | Public image hosting for both services |
| **Orchestration** | Kubernetes | 1.28+ | Cluster management, scheduling, self-healing |
| **Local cluster** | Minikube | 1.32+ | Single-node Kubernetes cluster for development |
| **Ingress controller** | ingress-nginx | 1.9+ | Layer-7 routing and load balancing |
| **Metrics pipeline** | Kubernetes Metrics Server | 0.7+ | CPU/memory data source for the HPA |
| **Base image** | python:3.11-slim | — | Minimal ~60 MB Python runtime image |

---

## Prerequisites

Before cloning, make sure the following tools are installed and working on your machine.

| Tool | Minimum version | Install guide | Purpose |
|------|----------------|---------------|---------|
| Docker Desktop / Engine | 24.0 | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) | Build images and run the container daemon |
| Minikube | 1.32 | [minikube.sigs.k8s.io/docs/start](https://minikube.sigs.k8s.io/docs/start/) | Local single-node Kubernetes cluster |
| kubectl | 1.28 | [kubernetes.io/docs/tasks/tools](https://kubernetes.io/docs/tasks/tools/) | Kubernetes CLI — apply manifests, inspect resources |
| Git | 2.x | [git-scm.com](https://git-scm.com/) | Clone this repository |

Verify your environment:

```bash
docker --version        # Docker version 24.x.x or higher
minikube version        # minikube version: v1.32.x or higher
kubectl version --client # Client Version: v1.28.x or higher
```

---

## Project Structure

```
devops-k8s-orchestration/
├── k8s/                          # Kubernetes manifests (apply in this order)
│   ├── namespace.yaml            # Step 1 — create the microservices namespace
│   ├── configmap.yaml            # Step 2 — non-sensitive env vars
│   ├── secret.yaml               # Step 3 — sensitive env vars
│   ├── api-deployment.yaml       # Step 4a — api-service Deployment (3 replicas)
│   ├── api-service.yaml          # Step 4b — api-service ClusterIP Service
│   ├── worker-deployment.yaml    # Step 5a — worker-service Deployment (2 replicas)
│   ├── worker-service.yaml       # Step 5b — worker-service ClusterIP Service
│   ├── ingress.yaml              # Step 6 — Ingress routing rules
│   └── hpa.yaml                  # Step 7 — HorizontalPodAutoscaler for api-service
└── services/
    ├── api-service/
    │   ├── app.py                # Flask application (gateway + health endpoints)
    │   ├── requirements.txt      # flask, gunicorn
    │   └── Dockerfile            # python:3.11-slim, non-root user, layer-cached deps
    └── worker-service/
        ├── app.py                # Flask application (work processor + health endpoints)
        ├── requirements.txt      # flask, gunicorn
        └── Dockerfile            # identical structure to api-service
```

---

## Setup Instructions

### Step 1 — Clone the repository

```bash
git clone https://github.com/NisargPawar/devops-k8s-orchestration.git
cd devops-k8s-orchestration
```

### Step 2 — Start Minikube

Start a local single-node cluster and enable the two addons this project requires:

```bash
# Start the cluster (adjust --cpus and --memory to suit your machine;
# at least 2 CPUs and 4 GB are recommended for the HPA demo).
minikube start --cpus=2 --memory=4096

# Enable the NGINX Ingress Controller so the cluster can process Ingress objects.
minikube addons enable ingress

# Enable the Metrics Server so the HPA can read CPU utilisation from Pods.
minikube addons enable metrics-server
```

Confirm both addons are running:

```bash
kubectl get pods -n ingress-nginx
kubectl get pods -n kube-system | grep metrics-server
```

Both should show `STATUS: Running` before proceeding.

### Step 3 — Apply all manifests

Apply in dependency order. Each resource must exist before the resources that reference it.

```bash
# 1. Namespace — must come first; every other resource specifies namespace: microservices.
kubectl apply -f k8s/namespace.yaml

# 2. ConfigMap and Secret — must exist before the Deployments that reference them
#    via envFrom. Applying them before the Deployments prevents a Pod from starting
#    in a CrashLoopBackOff because a referenced ConfigMap is missing.
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 3. Deployments and Services — order within this group does not matter because
#    Services discover Pods via label selectors at runtime, not at apply time.
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/worker-service.yaml

# 4. Ingress — applied after the Services it routes to exist, though Kubernetes
#    will reconcile it even if the backend Service appears later.
kubectl apply -f k8s/ingress.yaml

# 5. HPA — must be applied after the Deployment it targets, and the Metrics Server
#    must be running; otherwise the HPA enters an "unable to fetch metrics" state.
kubectl apply -f k8s/hpa.yaml
```

Or apply the entire directory at once (order is non-deterministic but Kubernetes retries until all dependencies resolve):

```bash
kubectl apply -f k8s/
```

### Step 4 — Verify the deployment

```bash
# Check all resources in the namespace are healthy.
kubectl get all -n microservices

# Expected output (replica counts may vary as the HPA adjusts):
#   NAME                                  READY   STATUS    RESTARTS   AGE
#   pod/api-service-<hash>-<hash>         1/1     Running   0          2m
#   pod/api-service-<hash>-<hash>         1/1     Running   0          2m
#   pod/api-service-<hash>-<hash>         1/1     Running   0          2m
#   pod/worker-service-<hash>-<hash>      1/1     Running   0          2m
#   pod/worker-service-<hash>-<hash>      1/1     Running   0          2m
#
#   NAME                     TYPE        CLUSTER-IP      PORT(S)
#   service/api-service      ClusterIP   10.x.x.x        80/TCP
#   service/worker-service   ClusterIP   10.x.x.x        8080/TCP
#
#   NAME                             READY   UP-TO-DATE   AVAILABLE
#   deployment.apps/api-service      3/3     3            3
#   deployment.apps/worker-service   2/2     2            2
#
#   NAME                                              REFERENCE              TARGETS   MINPODS   MAXPODS   REPLICAS
#   horizontalpodautoscaler.apps/api-service-hpa      Deployment/api-service   8%/50%   2         10        3
```

### Step 5 — Access the services

Minikube routes Ingress traffic through its IP rather than `localhost`. Get the IP and add a hosts entry:

```bash
# Get the Minikube cluster IP.
minikube ip
# e.g. 192.168.49.2

# Add to /etc/hosts (Linux/macOS) — replace with your actual minikube ip.
echo "$(minikube ip)  microservices.local" | sudo tee -a /etc/hosts

# On Windows, add the same line to C:\Windows\System32\drivers\etc\hosts
# as Administrator.
```

Alternatively, use `minikube tunnel` (requires sudo on Linux/macOS) which makes the Ingress controller's LoadBalancer IP reachable at `127.0.0.1`:

```bash
minikube tunnel
# Then use 127.0.0.1 instead of $(minikube ip) in the hosts file.
```

Test the endpoints:

```bash
# Root — welcome message from api-service.
curl http://microservices.local/

# Service metadata — version and environment.
curl http://microservices.local/api/info

# Liveness probe — used by Kubernetes; also useful for manual smoke tests.
curl http://microservices.local/health/live

# Readiness probe — includes a UTC timestamp to confirm the response is fresh.
curl http://microservices.local/health/ready

# Process route — shows the configured worker-service URL.
curl http://microservices.local/api/process
```

---

## kubectl Command Reference

These are the commands you will use repeatedly when working with this project. Each one is explained so you understand what it's doing, not just that it works.

### Applying and deleting resources

```bash
# Apply (create or update) a single manifest.
kubectl apply -f k8s/api-deployment.yaml

# Apply all manifests in the k8s/ directory at once.
kubectl apply -f k8s/

# Delete all resources in the namespace without deleting the namespace itself.
kubectl delete -f k8s/ --ignore-not-found

# Tear down everything — deleting the namespace cascades to every resource inside it.
kubectl delete namespace microservices
```

### Inspecting resources

```bash
# List every resource type in the namespace in one view.
kubectl get all -n microservices

# List Pods with additional columns (IP, Node).
kubectl get pods -n microservices -o wide

# Watch Pods update in real time (useful during a rolling update or scale event).
kubectl get pods -n microservices -w

# List Deployments and their current vs desired replica counts.
kubectl get deployments -n microservices

# Inspect the HPA — shows current CPU utilisation and replica count.
kubectl get hpa -n microservices

# Describe a resource for detailed status, events, and conditions.
# Replace <pod-name> with the actual name from `kubectl get pods`.
kubectl describe pod <pod-name> -n microservices
kubectl describe deployment api-service -n microservices
kubectl describe hpa api-service-hpa -n microservices

# View recent events (useful for debugging scheduling or probe failures).
kubectl get events -n microservices --sort-by=.lastTimestamp
```

### Logs and debugging

```bash
# Stream logs from a specific Pod.
kubectl logs <pod-name> -n microservices -f

# Stream logs from ALL Pods with a given label (fan-out across replicas).
kubectl logs -l app=api-service -n microservices -f

# Show the previous container's logs (useful after a crash/restart).
kubectl logs <pod-name> -n microservices --previous

# Open an interactive shell inside a running Pod for live debugging.
kubectl exec -it <pod-name> -n microservices -- /bin/sh

# Print all environment variables injected into a Pod
# (confirms ConfigMap and Secret values are correct).
kubectl exec <pod-name> -n microservices -- env | sort
```

### Scaling and updates

```bash
# Manually set a replica count (bypasses the HPA temporarily — HPA will override it).
kubectl scale deployment api-service --replicas=5 -n microservices

# Trigger a rolling update by updating the image tag.
kubectl set image deployment/api-service \
  api-service=nisarg2001009/api-service:v2.0.0 \
  -n microservices

# Watch the rollout progress step by step.
kubectl rollout status deployment/api-service -n microservices

# View rollout history (shows revision numbers and change causes).
kubectl rollout history deployment/api-service -n microservices

# Roll back to the previous revision if the new version has issues.
kubectl rollout undo deployment/api-service -n microservices

# Roll back to a specific revision.
kubectl rollout undo deployment/api-service --to-revision=1 -n microservices
```

### Port forwarding (bypassing the Ingress for direct access)

```bash
# Forward local port 8080 to a Service (useful when the Ingress isn't set up yet).
kubectl port-forward service/api-service 8080:80 -n microservices

# Forward to a specific Pod (useful for isolating one replica during debugging).
kubectl port-forward pod/<pod-name> 8080:8080 -n microservices
```

---

## Key Demonstrations

### 1. Rolling Update

A rolling update replaces old Pods with new ones gradually, ensuring the service never goes down during a deployment. This project's Deployments are configured with `maxUnavailable: 0` (never remove an old Pod until a new one is Ready) and `maxSurge: 1` (allow one extra Pod above the replica count during the rollout).

**Why this matters:** Without rolling updates, updating an application means a window of downtime while the old version is stopped and the new version starts. Rolling updates eliminate that window entirely.

**Trigger the update:**

```bash
# Update api-service from v1.0.0 to v2.0.0.
kubectl set image deployment/api-service \
  api-service=nisarg2001009/api-service:v2.0.0 \
  -n microservices

# Watch the rollout in real time. You will see new Pods appear (Running → Ready)
# before old Pods are terminated.
kubectl rollout status deployment/api-service -n microservices

# Simultaneously, watch Pod states in another terminal:
kubectl get pods -n microservices -w
```

**What you will observe:**

1. A new Pod is created with the v2.0.0 image (`maxSurge: 1` — replica count briefly becomes 4).
2. Kubernetes waits for the new Pod to pass its readiness probe (`/health/ready`).
3. Once the new Pod is Ready, one old Pod is terminated.
4. Steps 2–3 repeat until all 3 replicas are running v2.0.0.

**Roll back if needed:**

```bash
kubectl rollout undo deployment/api-service -n microservices
```

---

### 2. Self-Healing

Kubernetes continuously reconciles actual cluster state with the desired state declared in the Deployment. If a Pod is deleted (simulating a crash or node failure), the ReplicaSet controller detects the shortfall and creates a replacement immediately.

**Why this matters:** In a traditional deployment, a crashed process stays down until someone manually restarts it or an ops alert wakes someone at 3 AM. Kubernetes makes self-healing automatic.

**Simulate a Pod failure:**

```bash
# Get the names of the running api-service Pods.
kubectl get pods -n microservices -l app=api-service

# Delete one Pod to simulate a crash. The -l flag targets all matching Pods
# if you want to delete them all at once.
kubectl delete pod <pod-name> -n microservices

# Watch the replacement Pod be created immediately.
kubectl get pods -n microservices -w
```

**What you will observe:**

1. The deleted Pod's status changes to `Terminating`.
2. Within seconds, a new Pod appears in `Pending` → `ContainerCreating` → `Running` → `Ready`.
3. The replica count never drops below the desired count for more than a few seconds.
4. The Service's Endpoints list is updated automatically — traffic is never sent to the dead Pod.

**Simulate losing all Pods at once:**

```bash
kubectl delete pods -l app=api-service -n microservices
# All three are replaced simultaneously. The service experiences a brief interruption
# (this is why minReplicas=2 in the HPA is important — one Pod can survive a drain).
```

---

### 3. Horizontal Pod Autoscaling

The HPA watches CPU utilisation averaged across all api-service Pods. When the average exceeds 50% of the Pod's CPU request (100 m × 50% = 50 m per Pod), the HPA adds replicas. When utilisation drops and stays below the threshold for 5 minutes (the default stabilisation window), it removes replicas.

**The scaling formula:**

```
desiredReplicas = ceil( currentReplicas × (currentUtilisation / targetUtilisation) )

Example — 3 Pods at 80% average CPU, target 50%:
  ceil( 3 × (80 / 50) ) = ceil( 4.8 ) = 5 replicas  →  scale UP
```

**Why this matters:** Static replica counts either waste money (over-provisioned for quiet periods) or cause outages (under-provisioned for traffic spikes). An HPA makes capacity elastic with no manual intervention.

**Prerequisites:**

The Metrics Server must be running and collecting data. Verify it:

```bash
kubectl top pods -n microservices
# If this returns metrics, the Metrics Server is working.
# If it returns "error: Metrics API not available", wait 60 seconds and retry.
```

**Generate load to trigger scale-out:**

Open a second terminal and run a load loop:

```bash
# Get your Minikube IP.
MINIKUBE_IP=$(minikube ip)

# Send continuous requests to the api-service (runs for 3 minutes).
# Each request is a curl to /api/info — lightweight but enough to push CPU.
for i in $(seq 1 180); do
  curl -s "http://${MINIKUBE_IP}/api/info" > /dev/null
done
```

Or use `kubectl run` to generate load from inside the cluster:

```bash
kubectl run load-generator \
  --image=busybox \
  --restart=Never \
  -n microservices \
  -- sh -c "while true; do wget -q -O- http://api-service/api/info > /dev/null; done"
```

**Watch the HPA respond:**

```bash
# Watch CPU utilisation and replica count update in real time.
# The HPA syncs every 15 seconds; allow 30-60 seconds for the first scale event.
kubectl get hpa api-service-hpa -n microservices -w

# Also watch Pods being added.
kubectl get pods -n microservices -w
```

**Stop the load and watch scale-down:**

```bash
# Delete the load generator Pod.
kubectl delete pod load-generator -n microservices

# The HPA will wait 5 minutes (default stabilisation window) before scaling down
# to prevent thrashing on spiky traffic. Watch replicas decrease after that window.
kubectl get hpa api-service-hpa -n microservices -w
```

---

## Health Probes

Kubernetes uses two distinct HTTP probes to manage Pod lifecycle. They look similar but serve fundamentally different purposes and must never be conflated.

### Liveness probe — "Is the process stuck?"

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 15   # Wait before first check (time for Gunicorn to start).
  periodSeconds: 20          # Check every 20 s — infrequent to avoid noisy restarts.
  failureThreshold: 3        # Must fail 3 consecutive checks before restarting.
```

**Behaviour on failure:** Kubernetes restarts the container.

**What the endpoint does:** Returns `{"status": "alive"}`. It is intentionally minimal — no database calls, no downstream checks. A liveness probe that does too much work defeats its purpose: if the downstream dependency is down, you do not want to restart every Pod in the cluster.

**When you need it:** To recover from deadlocks, infinite loops, or any state where the process is running but permanently unable to serve requests. Without a liveness probe, a deadlocked Pod stays in service forever.

---

### Readiness probe — "Is the Pod ready to receive traffic?"

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5    # Shorter — we want traffic routed as soon as possible.
  periodSeconds: 10          # Check more frequently to re-add a recovered Pod quickly.
  failureThreshold: 3
```

**Behaviour on failure:** Kubernetes removes the Pod from the Service's Endpoints list. Traffic stops being sent to it. The Pod is NOT restarted.

**What the endpoint does:** Returns `{"status": "ready", "timestamp": "..."}`. The timestamp lets operators verify the check is live and not cached.

**When you need it:** During startup (the Pod is running but still warming up), during a rolling update (the new Pod is not ready yet), and when a transient dependency (like a downstream service) becomes unavailable. The Pod can recover without a restart — once it passes the probe again, Kubernetes re-adds it to the Endpoints list automatically.

---

### Key differences at a glance

| Aspect | Liveness | Readiness |
|--------|---------|-----------|
| **Failure action** | Restart the container | Remove from Service Endpoints |
| **Recovery** | Only via restart | Automatic when probe passes again |
| **Endpoint** | `/health/live` | `/health/ready` |
| **Initial delay** | 15 s (allows startup) | 5 s (add to rotation ASAP) |
| **Check frequency** | Every 20 s (conservative) | Every 10 s (responsive) |
| **Use case** | Deadlocks, fatal errors | Startup, transient overload, rolling updates |

---

## Docker Hub Images

Both images are published to Docker Hub and are publicly pullable.

| Service | Docker Hub | Tags |
|---------|-----------|------|
| **api-service** | [hub.docker.com/r/nisarg2001009/api-service](https://hub.docker.com/r/nisarg2001009/api-service) | `v1.0.0`, `v2.0.0` |
| **worker-service** | [hub.docker.com/r/nisarg2001009/worker-service](https://hub.docker.com/r/nisarg2001009/worker-service) | `v1.0.0` |

The two tags for api-service (`v1.0.0` and `v2.0.0`) exist specifically to demonstrate a rolling update — the Deployment starts on `v1.0.0` and is upgraded to `v2.0.0` without downtime.

**To rebuild and push your own images:**

```bash
# Build api-service.
docker build -t <your-dockerhub-username>/api-service:v1.0.0 services/api-service/
docker push <your-dockerhub-username>/api-service:v1.0.0

# Build worker-service.
docker build -t <your-dockerhub-username>/worker-service:v1.0.0 services/worker-service/
docker push <your-dockerhub-username>/worker-service:v1.0.0

# Update the image references in the manifests before applying.
# api-deployment.yaml:    image: <your-username>/api-service:v1.0.0
# worker-deployment.yaml: image: <your-username>/worker-service:v1.0.0
```

---

## Lessons Learned

**1. Resource requests are required, not optional.**
The HPA cannot compute utilisation without a Pod's CPU request. Set `resources.requests.cpu` on every container that you intend to autoscale — the HPA will silently do nothing until you do.

**2. Liveness and readiness probes serve distinct roles — conflating them causes incidents.**
A liveness probe that calls a downstream service will restart every Pod in the cluster when that service goes down. Keep liveness probes cheap and self-contained. Use readiness probes to express "I'm temporarily unable to serve traffic" without triggering a restart cascade.

**3. `maxUnavailable: 0` in a Deployment is meaningless without `minReplicas: 2` in the HPA.**
With a single replica and `maxUnavailable: 0`, a rolling update cannot start — it needs at least one running replica to preserve while bringing up the new one. Setting `minReplicas: 2` ensures the HPA never reduces below a count where a rolling update can proceed.

**4. Scale-down stabilisation is a feature, not a bug.**
The 5-minute default window before the HPA scales down feels slow the first time you watch it. It is intentional: CPU spikes on web services are bursty. Without it, a traffic spike followed by a quiet moment would create a scale-out/scale-in thrash loop that wastes scheduling resources and causes unnecessary Pod restarts.

**5. ConfigMaps and Secrets decouple config from the image.**
The same Docker image runs in development, staging, and production — only the ConfigMap values change. This is the Twelve-Factor App principle in practice. Never bake environment-specific values into an image tag.

**6. Namespaces make teardown clean.**
`kubectl delete namespace microservices` removes every resource in one command. If everything had been deployed to `default`, cleanup would mean hunting down individual resources or risking deleting something unrelated.

**7. The Ingress is not a Service.**
An Ingress resource on its own does nothing. It requires a running Ingress Controller to act on it. Forgetting to enable `minikube addons enable ingress` is the most common reason the Ingress appears to do nothing — `kubectl describe ingress` shows no address until the controller is running.
