-- Sources initiales (a executer apres schema.sql).
-- Les noms doivent correspondre a SourceConfig.name dans collector.py.
-- reliability : poids initial, ajuste ensuite par la boucle de feedback (bloc 11).
INSERT INTO sources (name, tier, base_url, language, fetch_method, poll_minutes, reliability) VALUES
  ('tunisienumerique', 'B', 'https://www.tunisienumerique.com', 'fr',    'http', 30, 0.75),
  ('mosaiquefm_ar',    'B', 'https://www.mosaiquefm.net',       'ar',    'http', 30, 0.80),
  ('tuniscope',        'B', 'https://www.tuniscope.com',        'mixed', 'http', 30, 0.75),
  ('businessnews',     'B', 'https://businessnews.com.tn',      'fr',    'http', 60, 0.75),
  ('lapresse',         'B', 'https://www.lapresse.tn',          'fr',    'http', 60, 0.75)
ON CONFLICT (name) DO NOTHING;
