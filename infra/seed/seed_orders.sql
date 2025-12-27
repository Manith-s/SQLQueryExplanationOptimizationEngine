CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  status TEXT NOT NULL,
  total_cents INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
-- Seed a few thousand rows for meaningful plans
INSERT INTO users (email) SELECT 'user'||g||'@example.com' FROM generate_series(1,5000) g
ON CONFLICT DO NOTHING;
INSERT INTO orders (user_id,status,total_cents,created_at)
SELECT (1 + (random()*4999)::int), (ARRAY['new','paid','shipped','cancelled'])[(1+random()*4)::int],
       (100 + (random()*50000)::int), now() - ((random()*365)::int || ' days')::interval
FROM generate_series(1,50000) g;












