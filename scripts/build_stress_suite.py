"""Reproducible author briefs; twists are left to the writer, never seeded as canon."""
import copy,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('fairytale','short_story','Dark fairy tale',4,350,6,'A city purchases dawn from a river spirit. The next sunrise fails, and a ferryman must decide whose unpaid promise to honor.'),
 ('ensemble','book','Political science-fiction mystery',4,1100,16,'A floating city votes on whether to abandon a failing district. A missing evacuation ledger connects a family dispute, a public promise and the city\u2019s power shortage.'),
 ('screenplay','screenplay','Contemporary heist thriller',2,800,8,'A ferry crew plans to recover a stolen relief fund during a guarded harbor transfer. Their least trusted collaborator has a conflicting obligation.'),
 ('theatre','stage_play','Dark comedy of manners',2,550,6,'A family convenes to inherit a municipal clock that nobody can afford to repair. Competing claims become an unexpectedly public negotiation.'),
 ('audio','audio_drama','Maritime psychological horror',2,450,6,'A harbor radio operator hears a rescue request using a missing relative\u2019s call sign. The crew must decide what evidence justifies leaving shelter.'),
 ('comic','comic_script','Hopeful science-fiction adventure',2,300,6,'A young courier must carry a fragile seed bank across a floating city while two factions dispute who gets the first harvest.'),
]
NAMES=['Mara Venn','Ivo Venn','Sera Holt','Tomas Reed','Nadi Vale','Oren Pike','Lea Sol','Bram Keel','Elin Frost','Davi Moss','Ruth Ash','Cass Wynn','Noor Bell','Pavel Gray','Uma Finch','Zed North']
JOBS=['ferryman','radio operator','city archivist','district physician','power engineer','harbor captain','courier','quartermaster','council speaker','mechanic','teacher','watch officer','botanist','union steward','accountant','night porter']
VOICES=['short practical questions','careful pauses and literal answers','formal corrections with dry humor','warm plain speech that hardens under pressure']
GOALS=['Keep the ferry open while refusing to choose which household is abandoned.','Establish whether a distress call is authentic without revealing a family debt.','Expose a falsified record while protecting the person who gave access.','Get patients across the water before medical supplies run out.','Secure an honest power ration without making the poorest district pay first.','Preserve crew loyalty while being ordered to deny passage.','Deliver a sealed parcel without surrendering the recipient\u2019s identity.','Account for missing supplies without scapegoating a subordinate.','Win public support without admitting an earlier promise cannot be kept.','Repair one failing mechanism while refusing an unsafe shortcut.','Keep displaced children together while negotiating space in another district.','Enforce an unpopular order while protecting a relative on the other side.','Keep a fragile seed collection alive without claiming ownership of the next harvest.','Protect workers without giving a rival faction control of the harbor.','Recover the chain of payment evidence without mistaking suspicion for proof.','Keep access to a closed building while demanding recognition for invisible work.']
FOCUS={
 'fairytale':'The river spirit and purchased dawn are the central supernatural conflict. Establish their observable effects and the bargain\u2019s limits. A mundane accounting correction alone cannot resolve the missing sunrise.',
 'ensemble':'The floating city, power shortage, evacuation decision and missing ledger must causally interact. Make the science-fiction setting tangible; do not reduce the story to ordinary paperwork.',
 'screenplay':'Across this episode the stolen relief fund and guarded harbor transfer drive the heist. The opening must establish a concrete crew tactic through observable preparation or action. The final scene enacts the attempt and its cost. A ferry permission dispute alone is not this story; do not require the final payoff in the opening.',
 'theatre':'The inherited municipal clock and family claims must stay central, with playable comedy and a consequential inheritance choice. Medical ferry bargaining must not replace the clock story.',
 'audio':'The dead father\u2019s call sign must become an audible mystery. By the ending, enact a consequential response to its evidence; merely locating a signal is not the promised climax.',
 'comic':'The fragile seed bank must appear visually and drive the courier\u2019s journey, faction pressure and consequential delivery choice. A dialogue-only ferry dispute is not the requested adventure.'}
CHARACTER_GOALS={
 'fairytale':[
  'Learn why purchased dawn failed and choose which household promise to honor without inventing another passage token.',
  'Test the river spirit\u2019s audible signs while hiding an unpaid family promise from Mara.',
  'Recover evidence of the original dawn bargain while protecting the person who exposed its altered record.',
  'Protect patients suffering under the unnatural cold without sacrificing another household\u2019s claim to dawn.',
  'Distinguish the spirit\u2019s limited power from a mundane failure before anyone stakes a life on a false remedy.',
  'Keep people from the black river while facing an order that conflicts with a personal vow.'],
 'screenplay':[
  'Commit the ferry to one concrete relief-fund recovery tactic while keeping its two-token limit real.',
  'Handle the crew\u2019s signals for the guarded transfer while concealing a conflicting household obligation.',
  'Authenticate a transfer record and exploit one demonstrated weakness without claiming the money is already recovered.',
  'Help recover the stolen fund while protecting a dependent whose needs conflict with the crew\u2019s timing.',
  'Operate the recovery gear within its visible limits and refuse a plan that quietly invents spare power.',
  'Choose whether to enforce the harbor transfer order or risk standing with the crew.'],
 'theatre':[
  'Contest who inherits the municipal clock and who must pay its repair debt without disguising the hearing as ferry business.',
  'Argue a sibling\u2019s claim to the clock while keeping an embarrassing household obligation out of public view.',
  'Read the clock estate\u2019s actual terms aloud and turn a claimant\u2019s polite evasion into a playable public negotiation.',
  'Claim a share of the clock inheritance while refusing to absorb the other claimants\u2019 repair bill.',
  'Establish the clock\u2019s repair burden and bargain over who will perform the work rather than offer a convenient free repair.',
  'Keep the clock inheritance hearing orderly while a private claim undermines that authority.'],
 'audio':[
  'Decide whether audible evidence from the missing relative\u2019s call justifies risking the ferry and its passengers.',
  'Verify the familiar call sign through sound while confronting a private family obligation.',
  'Compare the audible message against actual records without declaring an unproved caller identity.',
  'Weigh the possible rescue against the people already needing shelter and care.',
  'Test what the receiving equipment actually heard without inventing a third outbound transmission.',
  'Keep the crew in shelter until the evidence warrants a consequential departure.'],
 'comic':[
  'Help the courier move the visible fragile seed bank across the city without treating the delivery as an ordinary fare dispute.',
  'Relay only supported route information while choosing whether to expose a family obligation to the courier.',
  'Establish the competing harvest claims through a drawable confrontation without revealing a private recipient by fiat.',
  'Argue for a vulnerable district\u2019s first harvest while keeping the seed bank alive for other households.',
  'Protect the seed bank\u2019s observable storage limits during a consequential crossing.',
  'Decide whether to enforce a faction\u2019s crossing restriction or help the courier make a costly delivery.']}

def build():
 base=json.loads((ROOT/'examples/iron-man-alternate-origin.json').read_text())
 manifest=[]
 for slug,medium,genre,count,words,cast_size,premise in CASES:
  r=copy.deepcopy(base);project='stress-'+slug
  r['context_chars']=192000 if cast_size>=16 else 96000
  r['execution_policy']['max_hosted_requests']=6
  r['execution_policy']['hosted_project_attempts']=2
  r['execution_policy']['provider_outage_recovery'].update(buffer_seconds=600,extra_requests=12)
  r['api_roles']['memory_quality']='flash36'
  r['execution_policy']['hosted_routes']['memory_quality']=['flash36','flash','lite']
  r['execution_policy']['hosted_role_seconds']['memory_quality']=60
  r.update(project_id=project,universe_id=project,title='The Harbor Test: '+genre,medium=medium,chapters=count,scenes_per_chapter=1,words_per_scene=words,genre=genre,premise=premise+' Develop '+str(count)+' connected scenes. Invent the decisive discovery and climax yourself; no exact solution, culprit or twist is prescribed. Plant observable evidence before any revelation and make the climax change a relationship and consume a real advantage.',references=[],retrieval_query='dramatic irony competing obligations planted clues reversal consequences',reference_policy='Optional craft guidance only; never import another work\u2019s facts, genre, characters or style.',reader_experience='Distinct voices, escalating choices and a surprising but retrospectively supported turn.',pov='Present-tense filmable or performable action for scripts; close third-person past tense for prose. Limit private knowledge to actual witnesses.',tone_mood=genre+' with specific human stakes and varied emotional pacing.',sensory_detail='Select details appropriate to the medium; audio establishes action through sound, comics through drawable panels.',ending_tendency='Resolve this episode\u2019s main choice with an earned reversal and a lasting consequence; leave one meaningful unresolved thread.')
  r['style']={'narrator':'Follow the selected medium; do not add internal narration to scripts.','register':genre+'; original language, economical exposition, no generic moral.','wording':['No borrowed quotations, catchphrases or stock epic imagery.','Do not repeat earlier negotiations, discoveries or explanations.'],'interiority':'Show conflicting obligations through choices; prose may access only its focal viewpoint.','dialogue':'Distinct motives and speech patterns; use subtext and changing leverage.'}
  r['pov']=('Close third-person past tense for all narration; dialogue keeps its natural tense. Limit private knowledge to actual witnesses.' if medium in {'book','short_story'} else 'Present-tense filmable or performable action. Limit private knowledge to actual witnesses; follow the selected script medium.')
  r['style']['figurative_language']={'density':'sparse','devices':['concrete metaphor'],'image_domains':['harbor work','weather','household objects']}
  r['adaptation']={'strength':0,'mode':'structural_echo','max_active_sources_per_scene':0,'relationship':'Entirely original test world','preserve_user_choices':True,'preserve':['Author rules and private knowledge'],'divergence':'Invent solutions and climax; do not import film or epic canon.'}
  r['length_policy']['overflow']='advisory'
  r['length_policy']['policy']=f'{count} scenes, target {words} words each, minimum {int(words*.8)} for developed action. Longer scenes are acceptable; excess length alone is advisory, not grounds for rejection or rewriting. Quality, pacing, memory and non-repetition remain mandatory. Script cues count toward words; no padding.'
  r['characters']=[];r['initial_facts']=[]
  locations=['Ferry quay','Signal tower','Public archive','Council chamber']
  for i in range(cast_size):
   cid=f'c{i+1:02}';name=NAMES[i];job=JOBS[i]
   c=copy.deepcopy(base['characters'][i%len(base['characters'])])
   c.update(id=cid,name=name,goal=GOALS[i],value=['Reciprocity','Accuracy','Institutional accountability','Care for vulnerable people','Fair allocation','Loyalty to workers','Personal autonomy','Earned trust'][i%8],fear='Pursuing this goal at the expense of someone dependent on the '+job+'.',habitual_strategy=['Ask for proof','Trade a limited concession','Challenge an assumption','Withhold a personal cost'][i%4],limits='No unwitnessed secrets, unexplained travel or replacement of spent resources.',voice=VOICES[i%4]+'; concrete vocabulary from work as a '+job+'.',source_status='Original author-defined test character')
   if slug in CHARACTER_GOALS and i<len(CHARACTER_GOALS[slug]):c['goal']=CHARACTER_GOALS[slug][i]
   c['arc']={'starting_belief':'Duty can be discharged without personal loss.','old_strategy':c['habitual_strategy'],'pressure_test':c['goal'],'costly_choice':'Choose whom to trust and spend a real advantage.','possible_change':'Accept responsibility through action.'}
   c['contradiction']={'tension':'Public duty conflicts with private loyalty.'};c['emotional_behavior']={'pressure':'Speech and action diverge under pressure.'};c['voice_design']={'register':c['voice'],'examples':[['Who crosses first?','Count it before you promise it.'],['I heard the words. I need their meaning.','Give me a moment before I answer.'],['That is a claim, not a record.','An impressive signature on a very empty page.'],['Sit down. Your hands are shaking.','You can ask me. You cannot volunteer my family.']][i%4]}
   r['characters'].append(c)
   r['initial_facts'] += [
    {'kind':'event','text':name+' is alive at the opening.','known_by':['public'],'fact_key':'life:'+cid,'subject':cid,'life_state':'alive'},
    {'kind':'event','text':name+' begins at the '+locations[i%4]+'.','known_by':[cid],'fact_key':'location:'+cid},
    {'kind':'belief','text':name+' privately fears failing a dependent and has not confessed this fear.','known_by':[cid],'holder':cid,'fact_key':'belief:'+cid},
    {'kind':'event','text':name+' knows that an earlier city promise to their household remains unpaid; the meaning must be discovered through evidence.','known_by':[cid],'fact_key':'promise:'+cid}]
  ids=[c['id'] for c in r['characters']]
  r['initial_facts'] += [
   {'kind':'resource','text':'Mara holds exactly two single-use ferry passage tokens. Each token permits one ferry crossing; spent tokens cannot return.','known_by':['c01','c02'],'fact_key':'passage-tokens'},
   {'kind':'resource','text':'Ivo holds one portable radio with power for two outbound transmissions; receiving uses no counted transmission.','known_by':['c02'],'fact_key':'radio-charge'},
   {'kind':'event','text':'Mara and Ivo are siblings; neither has told the other their private household promise.','known_by':['c01','c02'],'fact_key':'family:venn'},
   {'kind':'event','text':'Sera alone knows that one archive ledger has an erased date; she has not identified who erased it or why.','known_by':['c03'],'fact_key':'erased-date'},
   {'kind':'event','text':'Travel among the four locations requires visible departure and arrival or an explicit interval of at least ten minutes.','known_by':['public'],'fact_key':'travel'},
   {'kind':'event','text':'The quay connects the districts; the tower relays calls; the archive holds records; the council chamber hosts public decisions.','known_by':['public'],'fact_key':'geography'}]
  r['world_rules']=['Only this brief and accepted on-page events are canon.','Private beliefs and clues cannot leak without an enacted disclosure.','Mara and Ivo remain siblings, with stable names and identities.','Every token or radio transmission is counted at its actual expenditure.','Physical travel, entrances and exits need an explicit cause and interval.','No retroactive backup power, extra token, secret tunnel or unearned rescue.','Plans, suspicions and hypotheses are not completed history.','Any extraordinary mechanism must be established with limits before solving a conflict.','Different medium presentation never changes underlying facts.','Costs, injuries, custody and consequences persist.','A twist needs an observable setup before payoff; no new retrospective facts to explain it.','Only the current scene participants may act unless a new entrance is established.']
  r['world_design']={'setting':'A harbor city with four districts linked by a ferry quay, signal tower, archive and council chamber.','technology':'Genre-appropriate tools constrained by the authored resource limits.','institutions':'Harbor authority, district council, archive and household obligations.','physical_systems':'A limited ferry service and radio; travel takes time.','deadlines':'The public decision occurs by the next dawn; establish changes to the deadline explicitly.'}
  r['plot_design']={'central_question':'Who bears the cost when a city keeps one promise by breaking another?','causal_dependencies':['Later scenes inherit actual knowledge, resources and changed relationships.','An invented clue must be enacted before the climax uses it.'],'subplots':[{'id':'venn','owner':'c02','question':'Can the siblings disagree without making each other expendable?','intersection':'The public choice forces a private concession.','removal_cost':'The decision loses its human stakes.'}],'alternatives_and_costs':['Spend a scarce advantage to disclose evidence, or protect a dependent while conceding leverage.']}
  goals=['Establish a contested objective and plant an ambiguous observable clue.','Develop the first consequence; challenge a tempting explanation without replaying discovery.','Bring separated interests together and force an irreversible commitment.','Invent and enact a supported climax reversal; show its immediate human and resource cost.'] if count==4 else ['Establish conflicting aims, a scarce advantage and an observable setup for a later reversal.','Invent a supported climax that changes the initial interpretation and resolves a concrete choice at a lasting cost.']
  r['scene_designs']=[]
  for i in range(count):
   others=[ids[(i*4+j)%len(ids)] for j in range(4)]
   participants=list(dict.fromkeys(['c01',*others]))
   r['scene_designs'].append({'id':f'ch{i+1:02}-sc01','pov':participants[0],'participants':participants,'location':locations[i%4],'setting':locations[i%4]+'; establish who arrived and what they carry.','time':f'Episode scene {i+1}; explicitly bridge the preceding exit state and travel time.','dramatic_function':goals[i],'development':'Invent specific action and resistance from current memory, including independent motives for supporting characters.','restrictions':'Do not decide the mystery by unexplained knowledge or restore a spent resource.','choice_and_consequence':goals[i]+' The exact invention and outcome are left to the model.'})
  r['chapter_contract']={'arc':'Escalation through distinct choices and a climax with earned surprise.','continuity':'Full memory, private knowledge, resource counts, travel and relationships remain authoritative.','ending':'Pay off an enacted setup, change leverage and retain a consequence.'}
  r['chapter_arcs']=goals
  r['quality_contract']=['Respect the selected medium, its headings, tense, cues and representable action.','Distinct voices and conflicting aims must cause choices, not inventory exposition.','Connect all scenes through full authoritative memory, with no repetition or reset.','Check exact custody, counted resources, character knowledge, chronology and geography.','Final climax must reinterpret an earlier enacted clue or choice; surprise cannot depend on a retroactively invented fact.','The original outcome is not prescribed; assess source-supported originality and consequences rather than conformity to a hidden plot.']
  r['quality_contract'].append(FOCUS[slug])
  for scene in r['scene_designs']:
   scene['development']=FOCUS[slug]+' '+scene['development']
   scene['dramatic_function']=FOCUS[slug]+' '+scene['dramatic_function']
  r['must_avoid']=['Imported Marvel, Homeric or other external canon.','Recapping an earlier negotiation instead of progressing.','Instant offstage construction, unexplained reserves, or leaks of private information.','Adding prose narration to a script or headings to prose.']
  r['creative_freedom'].update(protected_characters=['c01'],cast_limit=min(32,cast_size+2),max_new_per_scene=1,flexible_pov=True)
  r['execution_intent']={'authorized':'User requested sequential live stress tests across formats, genres, lengths and larger worlds.','workflow':'Full separate-runner pipeline; strict literary and factual gates; Gemini waits and no automatic local downgrade.'}
  (ROOT/f'examples/{project}.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
  manifest.append({'id':slug,'request_file':project,'scenes':count,'medium':medium,'words_per_scene':words,'cast':cast_size,'resume_case':None})
  if slug=='ensemble':
   continuation=copy.deepcopy(r);continuation['project_id']='stress-ensemble-continuation';continuation['title']+=': Aftermath'
   continuation['premise']='Continue the accepted harbor episode from its actual outcome. Do not replay the opening ledger mystery or assume its solution in advance. Across four new scenes, turn the prior climax\u2019s actual cost into a new public conflict. Preserve all history, cast, knowledge, spent resources and changed relationships. Invent a new earned climax from unresolved threads; never restore the opening state.'
   continuation['quality_contract'][-1]='The floating city and power constraints remain material. Develop the actual consequences of the preceding accepted episode; do not reopen a solved ledger mystery or repeat the evacuation vote as if no decision occurred.'
   for scene in continuation['scene_designs']:scene['development']=continuation['quality_contract'][-1]+' Invent specific new action and resistance from the actual current memory.'
   for scene in continuation['scene_designs']:scene['restrictions']+=' This is a continuation: use prior accepted history and never reset the world to this file\u2019s initial facts.'
   (ROOT/'examples/stress-ensemble-continuation.json').write_text(json.dumps(continuation,indent=2,ensure_ascii=False)+'\n')
 manifest.append({'id':'ensemble-continuation','request_file':'stress-ensemble-continuation','scenes':4,'medium':'book','words_per_scene':1100,'cast':16,'resume_case':'ensemble'})
 suite={'version':1,'per_run_timeout_minutes':45,'poll_seconds':30,'cases':manifest,'assessment':['strict automated audit','memory and private knowledge','repetition and form','source-supported setup and climax','distinct character agency','travel and resource continuity'],'literary_assessment':'Automated pass is not a human verdict on originality or literary quality; inspect saved output.'}
 (ROOT/'examples/stress-suite.json').write_text(json.dumps(suite,indent=2)+'\n')
 return suite

if __name__=='__main__':
 suite=build();print('Built',len(suite['cases']),'sequential cases;',sum(c['scenes'] for c in suite['cases']),'scenes.')
