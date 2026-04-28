ALTER TABLE influence_event
DROP CONSTRAINT IF EXISTS influence_event_event_family_check;

ALTER TABLE influence_event
ADD CONSTRAINT influence_event_event_family_check
CHECK (
    event_family IN (
        'money',
        'benefit',
        'campaign_support',
        'private_interest',
        'organisational_role',
        'access',
        'policy_behavior',
        'procurement',
        'grant',
        'appointment',
        'other'
    )
);
