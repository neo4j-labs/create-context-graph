import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Create Context Graph',
  tagline: 'AI agents with graph memory, scaffolded in seconds',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  markdown: {
    mermaid: true,
    // Docusaurus 3.10 + `future.v4: true` disables MDX v1 compatibility by
    // default; the docs still use HTML comments and `:::type Title`
    // admonitions, so keep the compat shims on until the content is migrated.
    mdx1Compat: {
      comments: true,
      admonitions: true,
      headingIds: true,
    },
  },
  themes: [
    '@docusaurus/theme-mermaid',
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexDocs: true,
        indexBlog: false,
        docsRouteBasePath: '/docs',
      },
    ],
  ],

  url: 'https://create-context-graph.dev',
  baseUrl: '/',

  organizationName: 'neo4j-labs',
  projectName: 'create-context-graph',

  onBrokenLinks: 'throw',

  plugins: [
    [
      '@docusaurus/plugin-client-redirects',
      {
        redirects: [
          {from: '/docs', to: '/docs/intro'},
          {from: '/docs/how-to/add-data-source', to: '/docs/how-to/import-saas-data'},
          {from: '/docs/how-to/customize-domain', to: '/docs/how-to/add-custom-domain'},
          {from: '/docs/how-to/query-context-graph', to: '/docs/intro'},
        ],
      },
    ],
  ],

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/neo4j-labs/create-context-graph/tree/main/docs/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Create Context Graph',
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/docs/reference/cli-options',
          label: 'CLI Reference',
          position: 'left',
        },
        {
          type: 'html',
          position: 'right',
          value: '<code style="font-size:12px;padding:4px 8px;background:rgba(99,102,241,0.1);border-radius:4px;color:var(--ifm-color-primary);font-family:JetBrains Mono,monospace">uvx create-context-graph</code>',
        },
        {
          href: 'https://github.com/neo4j-labs/create-context-graph',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    announcementBar: {
      id: 'version_banner',
      content: '📦 You are viewing docs for <b>create-context-graph v0.9.5</b>',
      isCloseable: true,
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {label: 'Getting Started', to: '/docs/intro'},
            {label: 'Quick Start', to: '/docs/quick-start'},
            {label: 'Tutorials', to: '/docs/tutorials/first-context-graph-app'},
            {label: 'How-To Guides', to: '/docs/how-to/import-saas-data'},
            {label: 'CLI Reference', to: '/docs/reference/cli-options'},
            {label: 'YAML Schema', to: '/docs/reference/ontology-yaml-schema'},
            {label: 'Explanation', to: '/docs/explanation/why-context-graphs'},
          ],
        },
        {
          title: 'Community',
          items: [
            {label: 'Neo4j Community Forum', href: 'https://community.neo4j.com/'},
            {label: 'GitHub Issues', href: 'https://github.com/neo4j-labs/create-context-graph/issues'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'Neo4j Labs', href: 'https://neo4j.com/labs/'},
            {label: 'neo4j-agent-memory', href: 'https://github.com/neo4j-labs/agent-memory'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'License (Apache 2.0)', href: 'https://github.com/neo4j-labs/create-context-graph/blob/main/LICENSE'},
            {label: 'Changelog', href: 'https://github.com/neo4j-labs/create-context-graph/releases'},
            {label: 'Contributing', href: 'https://github.com/neo4j-labs/create-context-graph/blob/main/CONTRIBUTING.md'},
          ],
        },
      ],
      copyright: `Copyright ${new Date().getFullYear()} Neo4j Labs. Open source under Apache 2.0. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'toml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
