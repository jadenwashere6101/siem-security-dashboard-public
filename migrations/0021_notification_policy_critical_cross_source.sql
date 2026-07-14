ALTER TABLE notification_policy
ADD COLUMN IF NOT EXISTS critical_cross_source_destination TEXT NOT NULL
    DEFAULT 'Critical / Cross-Source Security destination'
    CHECK (btrim(critical_cross_source_destination) <> '');
