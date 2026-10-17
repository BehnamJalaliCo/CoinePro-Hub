import next from 'eslint-config-next';

const config = [
  ...next,
  { ignores: ['.next/**', 'src/generated/**', 'node_modules/**'] },
];

export default config;
