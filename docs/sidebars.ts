import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    'quick-start',
    {
      type: 'category',
      label: 'Tutorials',
      items: [
        'tutorials/first-context-graph-app',
        'tutorials/customizing-domain-ontology',
        'tutorials/linear-context-graph',
      ],
    },
    {
      type: 'category',
      label: 'How-To Guides',
      items: [
        'how-to/import-saas-data',
        'how-to/add-custom-domain',
        'how-to/switch-agent-frameworks',
        'how-to/use-neo4j-aura',
        'how-to/use-neo4j-local',
        'how-to/use-docker',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: [
        'reference/cli-options',
        'reference/ontology-yaml-schema',
        'reference/generated-project-structure',
        'reference/framework-comparison',
        'reference/domain-catalog',
      ],
    },
    {
      type: 'category',
      label: 'Explanation',
      items: [
        'explanation/how-domain-ontologies-work',
        'explanation/three-memory-types',
        'explanation/why-context-graphs',
      ],
    },
  ],
};

export default sidebars;
