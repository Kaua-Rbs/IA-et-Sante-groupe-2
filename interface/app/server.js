// Point d'entrée de production : lance le serveur adapter-node (build/) en lisant ORIGIN au
// démarrage plutôt qu'au build, pour qu'une même image serve n'importe quelle URL publique.
// adapter-node ne lit l'origine qu'au build ; à défaut, il la déduit des en-têtes indiqués par
// HOST_HEADER et PROTOCOL_HEADER. On les fait pointer vers des en-têtes internes, réécrits sur
// chaque requête : un client ne peut pas imposer une autre origine (protection CSRF).
// Sans ORIGIN : origine déduite de l'en-tête Host, en supposant https.
const origin = process.env.ORIGIN ? new URL(process.env.ORIGIN) : null;

if (origin) {
	process.env.HOST_HEADER = 'x-kyst-origin-host';
	process.env.PROTOCOL_HEADER = 'x-kyst-origin-proto';
	delete process.env.PORT_HEADER;
}

const { server } = await import('./build/index.js');

if (origin) {
	server.prependListener('request', (req) => {
		req.headers['x-kyst-origin-host'] = origin.host;
		req.headers['x-kyst-origin-proto'] = origin.protocol.slice(0, -1);
	});
}
