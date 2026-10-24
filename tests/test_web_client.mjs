import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/js/api.js',import.meta.url));
const {StoryforgeClient,ApiError} = await import(`data:text/javascript;base64,${source.toString('base64')}`);
const nativeFetch=globalThis.fetch;
async function mocked(fn,run){globalThis.fetch=fn;try{await run();}finally{globalThis.fetch=nativeFetch;}}
const client=()=>new StoryforgeClient({baseUrl:'http://localhost:8000/',token:'demo',timeoutMs:30});

test('JSON requests preserve body, auth and URL escaping',async()=>{
 await mocked(async(url,options)=>{
  assert.equal(url,'http://localhost:8000/api/v1/requests/a%2Fb%20%CE%A9');
  assert.equal(options.headers.Authorization,'Bearer demo');
  return new Response(JSON.stringify({title:'雪 and Ω'}));
 },async()=>assert.equal((await client().getRequest('a/b Ω')).title,'雪 and Ω'));
 await mocked(async(url,options)=>{
  assert.equal(options.method,'POST');assert.deepEqual(JSON.parse(options.body),{mode:'sequential'});
  return new Response(JSON.stringify({run_id:1}),{status:202});
 },async()=>assert.equal((await client().startRun({mode:'sequential'})).run_id,1));
});
test('HTTP and non-JSON proxy errors remain actionable API errors',async()=>{
 for(const [status,body] of [[401,JSON.stringify({detail:'Bad token'})],[422,JSON.stringify({detail:[{msg:'Bad scene count'}]})],[502,'<html>Gateway failure</html>'],[200,'broken JSON']]){
  await mocked(async()=>new Response(body,{status}),async()=>{
   await assert.rejects(client().health(),e=>e instanceof ApiError && e.status===status && !e.message.includes('Unexpected token'));
  });
 }
});
test('network failures reset the status, timeouts never retry a POST',async()=>{
 let count=0;const api=client();api.lastStatus=200;
 await mocked(async()=>{throw new TypeError('offline')},async()=>{
  await assert.rejects(api.health(),e=>e.status===0);assert.equal(api.lastStatus,null);
 });
 await mocked((url,{signal})=>new Promise((resolve,reject)=>{count++;signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')));}),async()=>{
  await assert.rejects(api.startRun({mode:'sequential'}),e=>e.status===0 && e.message.includes('may still have started'));
 });
 assert.equal(count,1);
});
test('artifact download handles binary content and transport failures',async()=>{
 await mocked(async()=>new Response(new Uint8Array([80,75,3,4])),async()=>assert.equal((await client().downloadArtifact(1,'a b')).size,4));
 await mocked(async()=>{throw new TypeError('offline')},async()=>assert.rejects(client().downloadArtifact(1,'x'),e=>e instanceof ApiError && e.status===0));
});
async function watch(chunks,{expectError=false}={}){
 let cancelled=false;const seen=[];
 const stream=new ReadableStream({start(controller){for(const bytes of chunks)controller.enqueue(bytes);controller.close();},cancel(){cancelled=true;}});
 await mocked(async()=>new Response(stream),async()=>{
  await new Promise((resolve,reject)=>client().watchRun(1,{
   onRun:r=>seen.push(r),onEnd:()=>expectError?reject(new Error('Unexpected success')):resolve(),
   onError:e=>expectError?resolve():reject(e)
  }));
 });
 return seen;
}
test('SSE handles CRLF, multiline data, UTF-8 byte boundaries and end',async()=>{
 const bytes=new TextEncoder().encode('event: run\r\ndata: {"id":1,\r\ndata: "title":"雪 Ω"}\r\n\r\nevent: end\r\ndata: {}\r\n\r\n');
 const seen=await watch([...bytes].map(x=>new Uint8Array([x])));
 assert.deepEqual(seen,[{id:1,title:'雪 Ω'}]);
});
test('SSE reports truncated or malformed streams as errors',async()=>{
 await watch([new TextEncoder().encode('event: run\ndata: {"id":1}\n\n')],{expectError:true});
 await watch([new TextEncoder().encode('event: run\ndata: invalid\n\n')],{expectError:true});
});
test('ending or stopping a watcher releases its reader and ignores late data',async()=>{
 let cancelled=false,deliver,seen=0;
 const stream=new ReadableStream({start(c){deliver=c},cancel(){cancelled=true}});
 await mocked(async()=>new Response(stream),async()=>{
  const stop=client().watchRun(1,{onRun:()=>seen++});await new Promise(r=>setTimeout(r,0));
  stop();deliver.enqueue(new TextEncoder().encode('event: run\ndata: {}\n\n'));await new Promise(r=>setTimeout(r,5));
 });
 assert.equal(seen,0);assert.equal(cancelled,true);
});
