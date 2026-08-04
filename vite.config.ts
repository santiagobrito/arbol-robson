import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { defineConfig, type Plugin } from 'vite';

/**
 * En produccion nginx sirve /data/ desde el volumen montado. En desarrollo no
 * hay nginx, asi que este plugin expone la carpeta ./data del repositorio en
 * esa misma ruta y la app no necesita saber en que entorno corre.
 */
function serveDataDir(): Plugin {
  const root = join(process.cwd(), 'data');
  return {
    name: 'serve-data-dir',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const requested = decodeURIComponent((req.url ?? '/').split('?')[0]);
        const file = join(root, normalize(requested).replace(/^(\.\.[/\\])+/, ''));
        if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) {
          next();
          return;
        }
        res.setHeader(
          'Content-Type',
          extname(file) === '.ged' ? 'text/plain; charset=utf-8' : 'application/octet-stream',
        );
        createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [serveDataDir()],
  build: {
    target: 'es2022',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  // topola se publica en CommonJS: hay que prebundlearla para el dev server.
  optimizeDeps: {
    include: ['topola'],
  },
  server: {
    host: true,
    port: 5173,
  },
});
