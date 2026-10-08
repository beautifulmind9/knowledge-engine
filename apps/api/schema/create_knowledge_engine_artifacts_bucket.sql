-- Reference definition only. Apply separately with an administrative connection.
-- Private server-side access; deliberately no anon/authenticated access policies.
INSERT INTO storage.buckets (id, name, public)
VALUES ('knowledge-engine-artifacts', 'knowledge-engine-artifacts', false)
ON CONFLICT (id) DO UPDATE SET public = false;
