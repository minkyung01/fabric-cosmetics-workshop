-- Run in the SQL database sqldb_cos, NOT its read-only SQL analytics endpoint.
IF SCHEMA_ID(N'serving') IS NULL
    EXEC(N'CREATE SCHEMA serving');
GO

IF OBJECT_ID(N'serving.review_request', N'U') IS NULL
BEGIN
    CREATE TABLE serving.review_request (
        request_id nvarchar(200) NOT NULL PRIMARY KEY,
        event_id nvarchar(160) NOT NULL,
        material_code nvarchar(40) NOT NULL,
        target_type nvarchar(40) NOT NULL,
        target_id nvarchar(80) NOT NULL,
        assignee_team nvarchar(80) NOT NULL,
        slack_days int NOT NULL,
        suggestion nvarchar(1000) NOT NULL,
        request_status nvarchar(20) NOT NULL DEFAULT N'요청됨',
        source_requested_by nvarchar(256) NOT NULL,
        source_requested_at datetime2(6) NOT NULL,
        published_at datetime2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at datetime2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_review_status CHECK (request_status IN (N'요청됨', N'검토중')),
        CONSTRAINT UQ_review_event_target UNIQUE (event_id, target_id)
    );
    CREATE INDEX IX_review_team_status
        ON serving.review_request (assignee_team, request_status);
END;
GO

IF OBJECT_ID(N'serving.workflow_history', N'U') IS NULL
BEGIN
    CREATE TABLE serving.workflow_history (
        history_id bigint IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        request_id nvarchar(200) NOT NULL
            REFERENCES serving.review_request(request_id),
        old_status nvarchar(20) NOT NULL,
        new_status nvarchar(20) NOT NULL,
        changed_by nvarchar(256) NOT NULL,
        changed_at datetime2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

CREATE OR ALTER PROCEDURE serving.usp_publish_reviews
    @event_id nvarchar(160),
    @expected_count int,
    @requests nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    IF NULLIF(@event_id, N'') IS NULL OR @expected_count IS NULL OR @expected_count <= 0
        THROW 51000, 'An event and a positive approved request count are required.', 1;
    IF ISJSON(@requests) <> 1 OR @requests IS NULL
        THROW 51001, 'Requests must be valid JSON.', 1;

    DECLARE @source TABLE (
        request_id nvarchar(200) NOT NULL PRIMARY KEY,
        material_code nvarchar(40) NOT NULL,
        target_type nvarchar(40) NOT NULL,
        target_id nvarchar(80) NOT NULL UNIQUE,
        assignee_team nvarchar(80) NOT NULL,
        slack_days int NOT NULL,
        suggestion nvarchar(1000) NOT NULL,
        request_status nvarchar(20) NOT NULL,
        requested_by nvarchar(256) NOT NULL,
        requested_at datetime2(6) NOT NULL
    );
    INSERT INTO @source
    SELECT request_id, material_code, target_type, target_id, assignee_team,
           slack_days, suggestion, request_status, requested_by, requested_at
    FROM OPENJSON(@requests) WITH (
        request_id nvarchar(200),
        material_code nvarchar(40),
        target_type nvarchar(40),
        target_id nvarchar(80),
        assignee_team nvarchar(80),
        slack_days int,
        suggestion nvarchar(1000),
        request_status nvarchar(20),
        requested_by nvarchar(256),
        requested_at datetime2(6)
    );
    IF (SELECT COUNT(*) FROM @source) <> @expected_count
        THROW 51002, 'Approved count and publication row count differ.', 1;
    IF EXISTS (
        SELECT 1 FROM @source
        WHERE request_status <> N'요청됨'
           OR request_id <> CONCAT(N'RR-', @event_id, N'-', target_id)
    )
        THROW 51003, 'Only approved request snapshots with matching IDs can be published.', 1;

    BEGIN TRY
        BEGIN TRANSACTION;
        IF EXISTS (
            SELECT 1 FROM serving.review_request AS r WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN @source AS s ON r.request_id = s.request_id
            WHERE r.event_id <> @event_id OR r.target_id <> s.target_id
               OR r.material_code <> s.material_code
        )
            THROW 51004, 'A request ID already belongs to a different source.', 1;

        -- Insert only: republishing must not undo the workflow state owned by SQL.
        INSERT INTO serving.review_request (
            request_id, event_id, material_code, target_type, target_id, assignee_team,
            slack_days, suggestion, source_requested_by, source_requested_at
        )
        SELECT s.request_id, @event_id, s.material_code, s.target_type, s.target_id,
               s.assignee_team, s.slack_days, s.suggestion, s.requested_by, s.requested_at
        FROM @source AS s
        WHERE NOT EXISTS (
            SELECT 1 FROM serving.review_request AS r WITH (UPDLOCK, HOLDLOCK)
            WHERE r.request_id = s.request_id
        );
        DECLARE @inserted int = @@ROWCOUNT;
        COMMIT;
        SELECT @inserted AS inserted_count, @expected_count AS source_count;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH;
END;
GO

CREATE OR ALTER PROCEDURE serving.usp_start_review
    @request_id nvarchar(200)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        UPDATE serving.review_request
        SET request_status = N'검토중', updated_at = SYSUTCDATETIME()
        WHERE request_id = @request_id AND request_status = N'요청됨';
        IF @@ROWCOUNT <> 1
            THROW 51005, 'Request not found or no longer in the requested state.', 1;

        INSERT INTO serving.workflow_history (request_id, old_status, new_status, changed_by)
        VALUES (@request_id, N'요청됨', N'검토중', ORIGINAL_LOGIN());
        COMMIT;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0 ROLLBACK;
        THROW;
    END CATCH;
END;
GO
