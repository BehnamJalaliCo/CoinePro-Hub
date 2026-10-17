import next from 'eslint-config-next';

export default [
  ...next,
  { ignores: ['.next/**', 'src/generated/**', 'node_modules/**'] },
];
