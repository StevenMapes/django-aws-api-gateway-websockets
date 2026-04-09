# Architecture

```mermaid
graph TB
    subgraph "Client Side"
        WS[WebSocket Client<br/>Browser/App]
    end

    subgraph "AWS Infrastructure"
        APIGW[AWS API Gateway<br/>WebSocket API]
        subgraph "Routes"
            CONN[$connect Route]
            DISC[$disconnect Route]
            DEF[$default Route]
            CUST[Custom Routes<br/>e.g., 'action:chat']
        end
    end

    subgraph "Django Application"
        subgraph "URL Routing"
            URL[urls.py<br/>ws/&lt;slug:route&gt;]
        end
        
        subgraph "WebSocketView Class"
            DISPATCH[dispatch Method<br/>Route Dispatcher]
            SETUP[setup Method<br/>Parse JSON Body]
            
            subgraph "Security Checks"
                HDR[Header Validation]
                APIGW_CHK[API Gateway Check]
                UA[User Agent Check]
                PERM[Permission Check]
            end
            
            subgraph "Handler Methods"
                CONNECT[connect Handler<br/>Create Session]
                DISCONNECT[disconnect Handler<br/>Mark Disconnected]
                DEFAULT[default Handler<br/>User Implementation]
                CUSTOM[Custom Handlers<br/>Based on action/handler key]
            end
        end
        
        subgraph "Models & Database"
            APIGW_MODEL[(ApiGateway Model<br/>Gateway Config)]
            WSS_MODEL[(WebSocketSession Model<br/>Connection Tracking)]
            ROUTE_MODEL[(ApiGatewayAdditionalRoute<br/>Custom Routes)]
        end
        
        subgraph "Admin & Management"
            ADMIN[Django Admin]
            CMD[Management Commands<br/>createApiGateway<br/>createCustomDomain<br/>clearWebSocketSessions]
        end
    end

    subgraph "Messaging Flow"
        subgraph "Send Messages"
            SEND_UNI[Unicast<br/>websocket_session.send_message]
            SEND_MULTI[Multicast<br/>QuerySet.send_message<br/>Channel-based]
            SEND_BROAD[Broadcast<br/>All connected sessions]
        end
        
        BOTO3[Boto3 Client<br/>apigatewaymanagementapi]
    end

    %% Connection Flow
    WS -->|1. WebSocket Connect| APIGW
    APIGW -->|2. HTTP POST| CONN
    CONN -->|3. Route: 'connect'| URL
    URL --> DISPATCH
    DISPATCH --> SETUP
    SETUP --> HDR
    HDR --> APIGW_CHK
    APIGW_CHK -->|Validated| CONNECT
    CONNECT -->|Create Record| WSS_MODEL
    CONNECT -->|Link User & Channel| WSS_MODEL
    WSS_MODEL -->|200 OK| APIGW
    APIGW -->|Connection Established| WS

    %% Message Flow
    WS -->|4. Send Message<br/>action: 'chat'| APIGW
    APIGW -->|5. Route via<br/>route_selection_expression| DEF
    DEF -->|6. HTTP POST| URL
    URL --> DISPATCH
    DISPATCH --> SETUP
    SETUP --> UA
    UA --> PERM
    PERM -->|Load Session| WSS_MODEL
    PERM -->|Determine Handler| CUSTOM
    CUSTOM -->|Process Logic| CUSTOM
    
    %% Disconnect Flow
    WS -->|7. Disconnect| APIGW
    APIGW -->|8. HTTP POST| DISC
    DISC --> URL
    URL --> DISPATCH
    DISPATCH --> DISCONNECT
    DISCONNECT -->|Mark connected=False| WSS_MODEL

    %% Server to Client
    CUSTOM -.->|Send Response| SEND_UNI
    CUSTOM -.->|Broadcast to Channel| SEND_MULTI
    SEND_UNI --> BOTO3
    SEND_MULTI --> BOTO3
    BOTO3 -->|post_to_connection| APIGW
    APIGW -->|Push Message| WS

    %% Admin/Management
    ADMIN -->|Configure & Deploy| APIGW_MODEL
    ADMIN -->|Create Gateway| APIGW
    CMD -->|Setup Infrastructure| APIGW_MODEL
    APIGW_MODEL -.->|Reference| WSS_MODEL
    ROUTE_MODEL -.->|Extends| APIGW_MODEL

    %% Styling
    classDef clientClass fill:#e1f5ff,stroke:#0366d6
    classDef awsClass fill:#ff9900,stroke:#cc7a00
    classDef djangoClass fill:#0c4b33,stroke:#092e20,color:#fff
    classDef modelClass fill:#ffd700,stroke:#b8860b
    classDef messageClass fill:#90ee90,stroke:#228b22
    
    class WS clientClass
    class APIGW,CONN,DISC,DEF,CUST awsClass
    class URL,DISPATCH,SETUP,HDR,APIGW_CHK,UA,PERM,CONNECT,DISCONNECT,DEFAULT,CUSTOM,ADMIN,CMD djangoClass
    class APIGW_MODEL,WSS_MODEL,ROUTE_MODEL modelClass
    class SEND_UNI,SEND_MULTI,SEND_BROAD,BOTO3 messageClass
```
## Architecture Overview
This Django package enables WebSocket functionality using AWS API Gateway with the following key components:
### **Core Flow**
1. **Connection Phase ($connect)**
    - Client initiates WebSocket connection to AWS API Gateway
    - API Gateway sends HTTP POST to Django view with route='connect'
    - `WebSocketView.connect()` validates headers, user authentication, and security
    - Creates record linking connection_id, user, and optional channel `WebSocketSession`
    - Returns 200 OK to establish connection

2. **Message Handling ($default or custom routes)**
    - Client sends JSON message with "action" or "handler" key
    - API Gateway routes based on (default: ) `route_selection_expression``$request.body.action`
    - Django `dispatch()` method selects appropriate handler method dynamically
    - Loads WebSocketSession, validates permissions, and processes request
    - Handler can send responses via `websocket_session.send_message()` using Boto3

3. **Disconnection ($disconnect)**
    - Client disconnects or connection times out
    - API Gateway notifies Django
    - `WebSocketView.disconnect()` marks session as `connected=False` in database

### **Key Features**
- **Session Management**: Tracks all WebSocket connections with user association
- **Channel Support**: Groups connections for multicast messaging
- **Permission Control**: Django permissions integration (, ) `permissions_required``all_permissions_required`
- **Message Patterns**:
    - **Unicast**: Send to specific connection via `websocket_session.send_message()`
    - **Multicast**: Send to channel via `WebSocketSession.objects.filter(channel_name='...').send_message()`
    - **Broadcast**: Send to all connected sessions

- **Class-Based Views**: Standard Django CBV pattern for WebSocket handling
- **Admin Integration**: Manage API Gateways, routes, and sessions via Django Admin
- **Management Commands**: CLI tools for infrastructure setup and maintenance