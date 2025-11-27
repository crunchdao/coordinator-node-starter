# Condor Game Backend

**Documentation:** Available in the `docs` directory (Markdown format) or accessible via **[http://localhost:8000](http://localhost:8000)** after running everything locally using `make deploy`.

## Deployement 
This project supports three distinct modes of operation. Use the **Makefile** to manage and launch the application in these modes.

---

## **Modes Overview**

1. **Production**  
   For deploying the application in a remote cluster with dependencies such as `webto3` and `model orchestrator`.
    - Uses: `.production.env`

2. **Local**  
   For testing and demonstrating the application locally with minimal dependencies.
    - Uses: `.local.env`

3. **Development**  
   For active development and debugging, where services are run manually or via the IDE.
    - Uses: `.dev.env`
    - Launch your IDE with `.dev.env` to ensure proper connection to dependent services
   
---

### **Commands**

Run the following commands based on your current mode:

### General Commands:

- **Deploy Services**:
  ```bash
  make deploy           # Local mode
  make dev deploy       # Development mode
  make production deploy  # Production mode   all?
  ```
- **Restart Services**:
  ```bash
  make restart
  ```
- **Stop Services**:
  ```bash
  make stop
  ```
- **Follow Logs**:
  ```bash
  make logs
  ```
- **Shutdown**:
  ```bash
  make down
  ```
- **Build Only**:
  ```bash
  make build
  ```

---