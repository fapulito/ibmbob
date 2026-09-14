> ## Documentation Index
> Fetch the complete documentation index at: https://docs.e2b.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# List sandboxes

> List all running sandboxes. Use GET /v2/sandboxes instead.



## OpenAPI

````yaml /openapi-public.yaml get /sandboxes
openapi: 3.1.0
info:
  title: E2B API
  version: 0.1.0
  description: >-
    Complete E2B developer API. Platform endpoints are served on api.e2b.app.
    Sandbox endpoints (envd) are served on the shared sandbox host
    (sandbox.e2b.app); target a specific sandbox with the E2b-Sandbox-Id and
    E2b-Sandbox-Port headers.
servers:
  - url: https://api.e2b.app
    description: E2B Platform API
security: []
tags:
  - name: Sandboxes
  - name: Templates
  - name: Tags
  - name: Volumes
  - name: Envd
  - name: Filesystem
  - name: Process
  - name: Teams
paths:
  /sandboxes:
    servers:
      - url: https://api.e2b.app
        description: E2B Platform API
    get:
      tags:
        - Sandboxes
      summary: List sandboxes
      description: List all running sandboxes. Use GET /v2/sandboxes instead.
      operationId: listSandboxes
      parameters:
        - name: metadata
          in: query
          description: >-
            Metadata query used to filter the sandboxes (e.g.
            "user=abc&app=prod"). Each key and values must be URL encoded.
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Successfully returned all running sandboxes
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ListedSandbox'
        '400':
          $ref: '#/components/responses/400'
        '401':
          $ref: '#/components/responses/401'
        '500':
          $ref: '#/components/responses/500'
      deprecated: true
      security:
        - ApiKeyAuth: []
components:
  schemas:
    ListedSandbox:
      required:
        - templateID
        - sandboxID
        - clientID
        - startedAt
        - cpuCount
        - memoryMB
        - diskSizeMB
        - endAt
        - state
        - envdVersion
      properties:
        templateID:
          type: string
          description: Identifier of the template from which is the sandbox created
        alias:
          type: string
          description: Alias of the template
        sandboxID:
          type: string
          description: Identifier of the sandbox
        clientID:
          type: string
          deprecated: true
          description: Identifier of the client
        startedAt:
          type: string
          format: date-time
          description: Time when the sandbox was started
        endAt:
          type: string
          format: date-time
          description: Time when the sandbox will expire
        cpuCount:
          $ref: '#/components/schemas/CPUCount'
        memoryMB:
          $ref: '#/components/schemas/MemoryMB'
        diskSizeMB:
          $ref: '#/components/schemas/DiskSizeMB'
        metadata:
          $ref: '#/components/schemas/SandboxMetadata'
        state:
          $ref: '#/components/schemas/SandboxState'
        envdVersion:
          $ref: '#/components/schemas/EnvdVersion'
        volumeMounts:
          type: array
          items:
            $ref: '#/components/schemas/SandboxVolumeMount'
      type: object
    CPUCount:
      type: integer
      format: int32
      minimum: 1
      description: CPU cores for the sandbox
    MemoryMB:
      type: integer
      format: int32
      minimum: 128
      description: Memory for the sandbox in MiB
    DiskSizeMB:
      type: integer
      format: int32
      minimum: 0
      description: Disk size for the sandbox in MiB
    SandboxMetadata:
      additionalProperties:
        type: string
        description: Metadata of the sandbox
      type: object
    SandboxState:
      type: string
      description: State of the sandbox
      enum:
        - running
        - paused
    EnvdVersion:
      type: string
      description: Version of the envd running in the sandbox
    SandboxVolumeMount:
      type: object
      properties:
        name:
          type: string
          description: Name of the volume
        path:
          type: string
          description: Path of the volume
      required:
        - name
        - path
    Error:
      required:
        - code
        - message
      properties:
        code:
          type: integer
          format: int32
          description: Error code
        error_code:
          type: string
          description: >-
            Machine-readable semantic error code. Not a closed set; initial
            values: sandbox_capacity_unavailable, sandbox_placement_timeout,
            sandbox_no_compatible_node, sandbox_create_failed,
            internal_server_error.
        message:
          type: string
          description: Error
      type: object
  responses:
    '400':
      description: Bad request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    '401':
      description: Authentication error
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    '500':
      description: Server error
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

````