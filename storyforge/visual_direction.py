"""Story-sensitive art direction shared by local and enhanced image prompts."""
import re

STYLES = {
    'Documentary film still': 'Observed live-action photography; motivated available light, restrained color, off-center staging, natural expressions and practical locations.',
    'Period film still': 'Tactile period cinema; plausible wardrobe construction, worn practical sets, era-appropriate objects, soft highlight rolloff and restrained film grain.',
    'Noir photography': 'Low-key black-and-white photography, motivated pools of light, textured shadows, selective focus and quiet negative space; retain the story era.',
    'Grounded science fiction': 'Practical-effects science fiction; functional equipment, legible construction, used surfaces, motivated instrument light and physically plausible scale.',
    'Gouache storybook': 'Opaque gouache on textured paper, simplified expressive shapes, a limited pigment palette, visible brush edges and intentional areas of unpainted paper.',
    'Ink and watercolor': 'Economical ink contours and transparent watercolor washes on cold-pressed paper; varied line weight, pigment pooling and selective detail.',
    'Oil painting': 'Traditional oil on canvas; purposeful brushwork, controlled edges, believable value structure, limited palette and subtly visible canvas weave.',
    'Pencil storyboard': 'Production storyboard drawn in graphite; loose construction lines, decisive silhouettes, readable eyelines and blocking, three-value shading; one shot, no grid.',
    'Cinematic realism': 'Restrained live-action film photography with motivated lighting, believable staging, practical materials and a considered lens perspective.',
}
RULES = [
    ('Gouache storybook', r'\b(fairy tale|storybook|bedtime|children|whimsical)\b'),
    ('Grounded science fiction', r'\b(spaceship|spacecraft|android|cyberpunk|orbital|starship|science fiction)\b'),
    ('Noir photography', r'\b(noir|detective|murder|crime|investigator)\b'),
    ('Period film still', r'\b(ancient|medieval|bronze|troy|victorian|historical|kingdom|knight)\b'),
    ('Ink and watercolor', r'\b(fantasy|enchanted|magic|dragon|sorcerer)\b'),
]


def art_direction(spec, sources):
    requested=spec.get('style','Auto - match story').strip()
    automatic=not requested or requested.lower() in ('auto','auto - match story')
    text=' '.join(source['text'] for source in sources).lower()
    matches=[]
    if automatic:
        if spec['kind']=='storyboard':
            chosen='Pencil storyboard'
        else:
            ranked=[]
            for order,(name,pattern) in enumerate(RULES):
                evidence=sorted(set(re.findall(pattern,text)))
                if evidence:ranked.append((len(evidence),-order,name,evidence))
            if ranked:
                _,_,chosen,matches=max(ranked)
            else:chosen='Documentary film still'
    else:chosen=requested
    guidance=STYLES.get(chosen,'Honor the requested medium with intentional composition, coherent materials and a consistent palette: '+chosen)
    if spec.get('natural_finish',True):
        if chosen in ('Gouache storybook','Ink and watercolor','Oil painting','Pencil storyboard'):
            guidance+=' Keep marks selective and purposeful, with natural variation in line and pigment; avoid airbrushed gradients, glossy digital surfaces and uniformly sharp detail.'
        else:
            guidance+=' Preserve natural skin texture, asymmetry and ordinary expressions; plausible anatomy and hand-object contact, gravity and lens perspective. Use material-specific wear and coherent shadows. Avoid waxy skin, beauty retouching, excessive HDR, oversaturation, arbitrary glow and synthetic-looking bokeh.'
    guidance+=' Preserve described character appearance, wardrobe, geography and era across shots. Choose a restrained palette from the setting and mood; do not add genre props unsupported by the text.'
    return {'style':chosen,'automatic':automatic,'reason':('Storyboard shot readability' if automatic and spec['kind']=='storyboard' else 'Story cues: '+', '.join(matches) if matches else 'Restrained default; no strong genre cues' if automatic else 'Your selected style'), 'guidance':guidance,'natural_finish':spec.get('natural_finish',True)}
