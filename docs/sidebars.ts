import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    'quick-start',
    'whats-new',
    {
      type: 'category',
      label: 'Tutorials',
      collapsed: false,
      items: [
        'tutorials/first-context-graph-app',
        'tutorials/customizing-domain-ontology',
        'tutorials/linear-context-graph',
        'tutorials/google-workspace-decisions',
        'tutorials/claude-code-sessions',
        'tutorials/import-chat-history',
      ],
    },
    {
      type: 'category',
      label: 'How-To Guides',
      collapsed: false,
      items: [
        'how-to/use-nams',
        'how-to/configure-memory-providers',
        'how-to/import-saas-data',
        'how-to/add-custom-domain',
        'how-to/switch-agent-frameworks',
        'how-to/use-neo4j-aura',
        'how-to/use-neo4j-local',
        'how-to/use-docker',
        'how-to/connect-claude-desktop',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: [
        'reference/cli-options',
        'reference/ontology-yaml-schema',
        'reference/generated-project-structure',
        'reference/framework-comparison',
        'reference/domain-catalog',
        'reference/google-workspace-schema',
        'reference/claude-code-schema',
        'reference/chat-import-schema',
      ],
    },
    {
      type: 'category',
      label: 'Explanation',
      collapsed: false,
      items: [
        'explanation/memory-backends',
        'explanation/ccg-edges',
        'explanation/how-domain-ontologies-work',
        'explanation/three-memory-types',
        'explanation/why-context-graphs',
        'explanation/how-decision-traces-work',
      ],
    },
  ],
};

export default sidebars;
