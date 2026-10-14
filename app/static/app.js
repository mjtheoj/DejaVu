const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

let currentUser = null;
let appConfig = null;
let selectedClaimReport = null;
let selectedLostReportForMatchId = null;
let lostReportOptionsRequest = 0;
let reportSubmitting = false;
let claimSubmitting = false;
let selectedEvidenceClaimId = null;
let selectedStorageReportId = null;
let selectedHandoverClaimId = null;
let selectedDecisionClaimId = null;
let selectedDecisionAction = null;
let claimDecisionSubmitting = false;
let selectedCloseReportId = null;
let selectedCloseReportType = null;

const CATEGORY_ICONS = {
  stationery: "▤", clothing: "◈", bags_wallets: "▣", accessories: "◇",
  electronics: "⌁", identity_documents: "▧", keys_access: "⌘",
  cash_jewellery: "✧", sports_instruments: "◎", other: "◌"
};
const STATUS_LABELS = {
  open: "Open", awaiting_intake: "Awaiting office intake", available: "Available at office",
  claim_approved: "Awaiting handover", pending: "Under review", disputed: "Disputed · review required",
  needs_more_evidence: "More evidence requested", approved_for_collection: "Ready for handover",
  rejected: "Not approved", returned: "Returned to owner", closed: "Closed", cancelled: "Withdrawn"
};
const escapeHTML = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

function explainError(data, fallback) {
  if (!data || !data.detail) return fallback || "Something went wrong.";
  if (Array.isArray(data.detail)) return data.detail.map((x) => x.msg || "Invalid value").join(" ");
  return String(data.detail);
}


let usingMockApi = false;
let mockNoticeShown = false;
let inspectedUser = null;
const MOCK_CATEGORIES = [
 {value:"stationery",label:"Stationery & books"},{value:"clothing",label:"Clothing & everyday items"},
 {value:"bags_wallets",label:"Bags & wallets"},{value:"accessories",label:"Personal accessories"},
 {value:"electronics",label:"Electronics"},{value:"identity_documents",label:"Identity documents & cards"},
 {value:"keys_access",label:"Keys & access cards"},{value:"cash_jewellery",label:"Cash & jewellery"},
 {value:"sports_instruments",label:"Sports equipment & instruments"},{value:"other",label:"Other"}
];
const MOCK_USERS = {
 student:{id:101,email:"student@lostlink.local",display_name:"Alex Chen",role:"student"},
 student2:{id:102,email:"student2@lostlink.local",display_name:"Maya Patel",role:"student"},
 office:{id:900,email:"office@lostlink.local",display_name:"Campus Office",role:"office"}
};
const mockStore={seeded:false,session:null,reports:[],claims:[],notifications:[],ledger:[],certificates:[],reportImages:{},evidenceImages:{}};
const mockCopy=value=>JSON.parse(JSON.stringify(value));
const mockTimestamp=daysAgo=>new Date(Date.now()-(daysAgo||0)*86400000).toISOString();
function seedMockStore(){
 if(mockStore.seeded)return; mockStore.seeded=true;
 const base={brand:null,primary_color:null,visible_features:null,occurred_at:mockTimestamp(1),location_block:"Block A",location_floor:"1",location_room:"A-101",location_area:"Library entrance",image_path:null,status:"available",value_band:"medium",sensitivity_level:1,verification_level:2,private_detail:"Staff-only identifying detail reserved for office review.",storage_location:"Lost & Found room · Cabinet A · Shelf 01",created_by:900,created_at:mockTimestamp(1),updated_at:mockTimestamp(1)};
 mockStore.reports=[
 {...base,id:"mock-found-backpack",public_ref:"LL-F-1024",report_type:"found",title:"Navy backpack",description:"Dark blue backpack with two front pockets and a silver zipper pull.",brand:"Wildcraft",primary_color:"Navy blue",visible_features:"Two front pockets; silver zipper pull",category:"bags_wallets",tag_id:"LL-CVR-2026-000101",private_detail:"Tiny stitched mark inside the left strap."},
 {...base,id:"mock-found-earbuds",public_ref:"LL-F-1025",report_type:"found",title:"Wireless earbuds case",description:"Black wireless earbud charging case found beside the library study area.",primary_color:"Black",visible_features:"Small white sticker on the back edge",category:"accessories",location_room:"",location_area:"Library study area",tag_id:"LL-CVR-2026-000102",private_detail:"Small white sticker on the back edge."},
 {...base,id:"mock-found-bottle",public_ref:"LL-F-1026",report_type:"found",title:"Steel water bottle",description:"Silver insulated bottle with a black cap and a scratch near the base.",primary_color:"Silver",visible_features:"Black cap; scratch near base",category:"accessories",location_block:"Block B",location_floor:"Ground",location_room:"",location_area:"Cafeteria",tag_id:"LL-CVR-2026-000103",private_detail:"Small dent underneath the base."},
 {...base,id:"mock-awaiting-umbrella",public_ref:"LL-F-1027",report_type:"found",title:"Grey folding umbrella",description:"Compact grey folding umbrella with a curved handle.",primary_color:"Grey",visible_features:"Curved handle",category:"clothing",status:"awaiting_intake",created_by:102,tag_id:null,storage_location:null,private_detail:null,location_block:"Block B",location_floor:"Ground",location_room:"",location_area:"Cafeteria entrance"},
 {...base,id:"mock-lost-backpack",public_ref:"LL-L-1024",report_type:"lost",title:"Dark blue backpack",description:"I lost a dark blue backpack with two front pockets around the library.",primary_color:"Navy blue",visible_features:"Two front pockets",category:"bags_wallets",status:"open",created_by:101,tag_id:null,storage_location:null,private_detail:null,location_area:"Library",location_room:"",verification_level:null},
 {...base,id:"mock-lost-bottle",public_ref:"LL-L-1025",report_type:"lost",title:"Silver insulated bottle",description:"A steel water bottle with black lid, last seen by cafeteria.",primary_color:"Silver",visible_features:"Black cap",category:"accessories",status:"open",created_by:102,tag_id:null,storage_location:null,private_detail:null,location_block:"Block B",location_floor:"Ground",location_room:"",location_area:"Cafeteria",verification_level:null}
 ];
 mockStore.claims=[{id:"mock-claim-backpack",report_id:"mock-found-backpack",lost_report_id:"mock-lost-backpack",claimant_id:101,claimant_name:"Alex Chen",claimant_email:MOCK_USERS.student.email,evidence:"I can identify a stitched mark inside the left strap and have a purchase receipt for the bag.",evidence_types:["distinctive_features","purchase_or_receipt"],status:"pending",appeal_note:null,appeal_count:0,reviewer_note:null,created_at:mockTimestamp(0),updated_at:mockTimestamp(0),verification_checks:[]}];
 mockStore.notifications=[
 {id:"mock-notice-match",user_id:101,event_key:"mock-match",title:"A possible item match was found",message:"A found backpack may match your open lost report LL-L-1024.",entity_type:"report",entity_id:"mock-lost-backpack",read_at:null,created_at:mockTimestamp(0)},
 {id:"mock-notice-intake",user_id:900,event_key:"mock-intake",title:"Found-item report awaiting intake",message:"A grey folding umbrella is waiting for physical intake.",entity_type:"report",entity_id:"mock-awaiting-umbrella",read_at:null,created_at:mockTimestamp(0)}
 ];
 mockStore.ledger=[
 {user_id:101,points:10,reason:"Found item received and tagged by the campus office",report_id:"mock-found-backpack",created_at:mockTimestamp(4)},
 {user_id:102,points:15,reason:"Verified campus contribution",report_id:"mock-found-bottle",created_at:mockTimestamp(2)}
 ];
 mockStore.certificates=[{id:"mock-cert-finder",user_id:101,tier:"Verified Finder",threshold_points:20,points_at_issue:20,serial:"LL-CERT-DEMO-0001",issued_at:mockTimestamp(2)}];
 mockStore.session=mockCopy(MOCK_USERS.student);
}
function enableMockMode(){
 usingMockApi=true;seedMockStore();
 if(!mockNoticeShown){mockNoticeShown=true;window.setTimeout(()=>{if($("#appModeNote"))$("#appModeNote").classList.remove("hidden");showToast("Backend unavailable. Interactive offline preview is active; changes will not persist.",false);},0);}
}
function mockNotify(userId,title,message,entityType,entityId,eventKey){
 const key=eventKey||("demo:"+title+":"+entityId+":"+Date.now());
 if(mockStore.notifications.some(n=>n.user_id===userId&&n.event_key===key))return;
 mockStore.notifications.unshift({id:"mock-notice-"+Math.random().toString(36).slice(2,10),user_id:userId,event_key:key,title,message,entity_type:entityType||null,entity_id:entityId||null,read_at:null,created_at:mockTimestamp(0)});
}
function mockReadBody(options){
 if(!options||!options.body||options.body instanceof FormData)return options&&options.body instanceof FormData?options.body:{};
 if(typeof options.body==="string"){try{return JSON.parse(options.body);}catch(_){return {};}}
 return options.body;
}
function mockReportView(report,internal){
 const sensitive=["identity_documents","keys_access"].includes(report.category)&&!internal, image=mockStore.reportImages[report.id]||null;
 const result={id:report.id,public_ref:report.public_ref,report_type:report.report_type,title:report.title,description:report.description,
 brand:report.brand,primary_color:report.primary_color,visible_features:report.visible_features,category:report.category,
 category_label:(MOCK_CATEGORIES.find(x=>x.value===report.category)||{}).label||report.category,occurred_at:report.occurred_at,
 location:[report.location_block,report.location_floor?"Floor "+report.location_floor:null,(internal||!sensitive)?report.location_room:null,report.location_area].filter(Boolean).join(" · ")||"Location not specified",
 location_block:report.location_block,location_floor:report.location_floor,location_room:internal?report.location_room:null,location_area:report.location_area,
 image_url:sensitive||!image?null:image,status:report.status,created_at:report.created_at,updated_at:report.updated_at};
 if(internal)Object.assign(result,{tag_id:report.tag_id,private_verification_detail:report.private_detail,value_band:report.value_band||"unknown",sensitivity_level:report.sensitivity_level||1,verification_level:report.verification_level,storage_location:report.tag_id?report.storage_location:null,created_by:report.created_by});
 if(report.report_type==="lost"&&currentUser&&currentUser.id===report.created_by)result.has_active_linked_claim=mockStore.claims.some(c=>c.lost_report_id===report.id&&["pending","disputed","needs_more_evidence","approved_for_collection"].includes(c.status));
 return result;
}
function mockClaimView(claim,internal){
 const report=mockStore.reports.find(r=>r.id===claim.report_id), linked=mockStore.reports.find(r=>r.id===claim.lost_report_id);
 const result={id:claim.id,status:claim.status,evidence_types:claim.evidence_types||[],evidence_image_available:Boolean(mockStore.evidenceImages[claim.id]),created_at:claim.created_at,updated_at:claim.updated_at,appeal_note:claim.appeal_note||null,appeal_count:claim.appeal_count||0,linked_lost_report:linked?{id:linked.id,public_ref:linked.public_ref,title:linked.title,status:linked.status}:null,report:report?mockReportView(report,internal):null};
 if(internal)Object.assign(result,{evidence:claim.evidence,claimant_name:claim.claimant_name,claimant_email:claim.claimant_email,reviewer_note:claim.reviewer_note||null});
 return result;
}
async function mockFileDataUrl(file){
 if(!file||!window.FileReader)return null;
 return await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||""));reader.onerror=()=>resolve(null);reader.readAsDataURL(file);});
}
function mockRequireOffice(){if(!currentUser||currentUser.role!=="office")throw new Error("Office staff access required.");}
function mockCertificateDownload(certificateId){
 const cert=mockStore.certificates.find(c=>c.id===certificateId&&(currentUser.role==="office"||c.user_id===currentUser.id));
 if(!cert){showToast("Certificate not found for this demo account.",true);return;}
 const safe=v=>String(v||"").replace(/[^\x20-\x7E]/g,"?").replace(/([\\()])/g,"\\$1");
 const lines=["LOSTLINK - CERTIFICATE OF RECOGNITION",cert.tier,"Awarded to "+currentUser.display_name,String(cert.points_at_issue)+" verified activity points","Certificate ID: "+cert.serial,"Issued: "+String(cert.issued_at).slice(0,10),"Demo preview - not an official college credential"];
 const stream="BT\n/F1 18 Tf\n60 740 Td\n("+safe(lines[0])+") Tj\n/F1 15 Tf\n0 -54 Td\n("+safe(lines[1])+") Tj\n/F1 11 Tf\n0 -40 Td\n("+safe(lines[2])+") Tj\n0 -26 Td\n("+safe(lines[3])+") Tj\n0 -24 Td\n("+safe(lines[4])+") Tj\n0 -20 Td\n("+safe(lines[5])+") Tj\n0 -42 Td\n("+safe(lines[6])+") Tj\nET";
 const objects=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>","<< /Length "+stream.length+" >>\nstream\n"+stream+"\nendstream"];
 let pdf="%PDF-1.4\n",offsets=[0];objects.forEach((obj,i)=>{offsets.push(pdf.length);pdf+=(i+1)+" 0 obj\n"+obj+"\nendobj\n";});
 const xref=pdf.length;pdf+="xref\n0 6\n0000000000 65535 f \n";for(let i=1;i<offsets.length;i++)pdf+=String(offsets[i]).padStart(10,"0")+" 00000 n \n";
 pdf+="trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"+xref+"\n%%EOF";
 const a=document.createElement("a"),url=URL.createObjectURL(new Blob([pdf],{type:"application/pdf"}));a.href=url;a.download="LostLink-"+cert.serial+".pdf";document.body.appendChild(a);a.click();a.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);showToast("Demo certificate PDF generated locally.",false);
}
async function mockApi(url,options){
 seedMockStore();const parsed=new URL(url,window.location.href),path=parsed.pathname,method=(options&&options.method||"GET").toUpperCase(),body=mockReadBody(options);
 if(path==="/api/config"&&method==="GET")return {demo_mode:true,points:{verified_intake:10,verified_return:5},certificate_milestones:[{tier:"Verified Finder",threshold:20},{tier:"Campus Helper",threshold:50},{tier:"Community Champion",threshold:100}],categories:mockCopy(MOCK_CATEGORIES),locations:{blocks:["Block A","Block B","Block C","Library","Cafeteria","Other / not sure"],floors:["Ground","1","2","3","Other / not sure"],note:"Interactive local preview"}};
 if(path==="/api/me"&&method==="GET"){mockStore.session=mockStore.session||mockCopy(MOCK_USERS.student);return {user:mockCopy(mockStore.session)};}
 if(path==="/api/login"&&method==="POST"){const email=String(body.email||"").toLowerCase(),user=email.includes("office")?MOCK_USERS.office:email.includes("student2")?MOCK_USERS.student2:MOCK_USERS.student;mockStore.session=mockCopy(user);return {user:mockCopy(user)};}
 if(path==="/api/logout"&&method==="POST"){mockStore.session=null;return {ok:true};}
 if(path==="/api/reports"&&method==="GET"){
  const q=String(parsed.searchParams.get("q")||"").trim().toLowerCase(),mine=parsed.searchParams.get("mine")==="true",internal=currentUser&&currentUser.role==="office";
  const filtered=mockStore.reports.filter(r=>{
   if(!internal&&mine&&r.created_by!==currentUser.id)return false;
   if(!internal&&!mine&&!(r.report_type==="found"&&r.status==="available"))return false;
   for(const [param,field] of [["report_type","report_type"],["category","category"]])if(parsed.searchParams.get(param)&&r[field]!==parsed.searchParams.get(param))return false;
   if(parsed.searchParams.get("block")&&!(r.location_block||"").toLowerCase().includes(parsed.searchParams.get("block").toLowerCase()))return false;
   if(parsed.searchParams.get("room")&&!(r.location_room||"").toLowerCase().includes(parsed.searchParams.get("room").toLowerCase()))return false;
   if(internal&&parsed.searchParams.get("status")&&r.status!==parsed.searchParams.get("status"))return false;
   if(parsed.searchParams.get("date_from")&&String(r.occurred_at||"")<parsed.searchParams.get("date_from"))return false;
   if(parsed.searchParams.get("date_to")&&String(r.occurred_at||"")>parsed.searchParams.get("date_to")+"T23:59:59")return false;
   if(q&&!([r.title,r.description,r.public_ref,r.location_area,r.brand,r.primary_color,r.visible_features,r.location_block,r.location_floor,r.location_room].join(" ").toLowerCase().includes(q)))return false;
   return true;
  }).sort((a,b)=>b.created_at.localeCompare(a.created_at)).slice(0,250);
  return {reports:filtered.map(r=>mockReportView(r,Boolean(internal)))};
 }
 if(path==="/api/reports"&&method==="POST"){
  if(!currentUser||currentUser.role!=="student")throw new Error("Submit reports from a student account.");
  if(String(body.title||"").trim().length<4||String(body.description||"").trim().length<10)throw new Error("Enter a meaningful item title and description.");
  const report={id:"mock-report-"+Math.random().toString(36).slice(2,10),public_ref:"LL-"+Math.random().toString(36).slice(2,8).toUpperCase(),report_type:body.report_type,title:String(body.title).trim(),description:String(body.description).trim(),brand:body.brand||null,primary_color:body.primary_color||null,visible_features:body.visible_features||null,category:body.category,occurred_at:body.occurred_at||mockTimestamp(0),location_block:body.location_block||"",location_floor:body.location_floor||"",location_room:body.location_room||"",location_area:body.location_area||"",image_path:null,status:body.report_type==="lost"?"open":"awaiting_intake",value_band:"unknown",sensitivity_level:1,verification_level:null,tag_id:null,storage_location:null,private_detail:null,created_by:currentUser.id,created_at:mockTimestamp(0),updated_at:mockTimestamp(0)};
  mockStore.reports.unshift(report);mockNotify(currentUser.id,body.report_type==="lost"?"Lost report submitted":"Found report submitted",body.report_type==="lost"?"Your lost report is saved.":"Your found report is waiting for office intake.","report",report.id,"report-created:"+report.id);
  if(report.report_type==="found")mockNotify(MOCK_USERS.office.id,"Found-item report awaiting intake","A new found-item report is waiting for physical office intake.","report",report.id,"found-report:"+report.id);
  return {report:mockReportView(report,currentUser.role==="office"),message:report.report_type==="lost"?"Lost report submitted.":"Found-item report submitted for office intake."};
 }
 let m=path.match(/^\/api\/reports\/([^/]+)\/(image|matches|intake|storage|close)$/);
 if(m){
  const id=decodeURIComponent(m[1]),action=m[2],report=mockStore.reports.find(r=>r.id===id);if(!report)throw new Error("Report not found.");
  if(action==="image"&&method==="POST"){const file=body instanceof FormData?body.get("file"):null,data=await mockFileDataUrl(file);if(data)mockStore.reportImages[id]=data;report.updated_at=mockTimestamp(0);return {report:mockReportView(report,currentUser.role==="office")};}
  if(action==="matches"&&method==="GET"){
   const candidates=mockStore.reports.filter(r=>r.report_type==="found"&&r.status==="available").map(r=>{
    const terms=(report.title+" "+report.description).toLowerCase().split(/\W+/).filter(x=>x.length>2),hay=(r.title+" "+r.description+" "+(r.primary_color||"")+" "+(r.visible_features||"")).toLowerCase(),overlap=terms.filter(term=>hay.includes(term)).length,score=Math.min(.94,.48+overlap*.055);
    return {...mockReportView(r,false),score,match_strength:score>=.72?"strong":score>=.45?"possible":"limited",match_reasons:["Descriptions contain overlapping item terms.","Category and reported location can help narrow review."],match_reasons_text:"Descriptions contain overlapping item terms."};
   }).sort((a,b)=>b.score-a.score).slice(0,5);return {matches:candidates};
  }
  if(action==="intake"&&method==="POST"){
   mockRequireOffice();if(report.report_type!=="found"||report.status!=="awaiting_intake"||body.confirmed_physical_receipt!==true)throw new Error("Confirm physical receipt for an item awaiting intake.");
   report.storage_location=String(body.storage_location||"").trim();if(report.storage_location.length<4)throw new Error("Enter a specific storage location.");
   report.private_detail=body.private_detail||null;report.value_band=body.value_band||"unknown";report.sensitivity_level=Number(body.sensitivity_level||1);
   const defaults={stationery:1,clothing:1,bags_wallets:2,accessories:2,electronics:3,identity_documents:4,keys_access:4,cash_jewellery:3,sports_instruments:2,other:3};
   report.verification_level=report.sensitivity_level>=3?4:Math.max(defaults[report.category]||3,report.sensitivity_level);
   report.tag_id="LL-CVR-"+new Date().getFullYear()+"-"+String(mockStore.reports.indexOf(report)+101).padStart(6,"0");report.status="available";report.updated_at=mockTimestamp(0);
   mockNotify(MOCK_USERS.office.id,"Intake confirmed","The item was tagged and placed into campus custody.","report",id,"intake:"+id);
   if(report.created_by!==MOCK_USERS.office.id){mockStore.ledger.unshift({user_id:report.created_by,points:10,reason:"Found item received and tagged by the campus office",report_id:id,created_at:mockTimestamp(0)});mockNotify(report.created_by,"Found item received and stored","Your item has been accepted by the campus office.","report",id,"intake-reward:"+id);}
   return {report:mockReportView(report,true),message:"Item received, tagged and stored."};
  }
  if(action==="storage"&&method==="POST"){mockRequireOffice();if(!report.tag_id)throw new Error("Only tagged items in custody can be moved.");report.storage_location=String(body.storage_location||"").trim();report.updated_at=mockTimestamp(0);return {report:mockReportView(report,true),message:"Storage location updated."};}
  if(action==="close"&&method==="POST"){if(!currentUser||currentUser.role!=="student"||report.created_by!==currentUser.id)throw new Error("Report not found.");if(report.report_type==="lost"&&report.status==="open")report.status="closed";else if(report.report_type==="found"&&report.status==="awaiting_intake"&&body.reason==="found_report_withdrawn")report.status="cancelled";else throw new Error("Only an open lost report or found report awaiting office intake can be closed.");report.updated_at=mockTimestamp(0);return {report:mockReportView(report,false),message:"Report closed."};}
 }
 if(path==="/api/claims"&&method==="GET"){const internal=currentUser&&currentUser.role==="office";return {claims:mockStore.claims.filter(c=>internal||c.claimant_id===currentUser.id).sort((a,b)=>b.created_at.localeCompare(a.created_at)).map(c=>mockClaimView(c,Boolean(internal)))};}
 if(path==="/api/claims"&&method==="POST"){
  if(!currentUser||currentUser.role!=="student")throw new Error("Claims must be submitted from a student account.");
  const report=mockStore.reports.find(r=>r.id===body.report_id);if(!report||report.report_type!=="found"||report.status!=="available")throw new Error("This item is not accepting claims.");
  if(report.created_by===currentUser.id)throw new Error("You cannot claim your own found-item report.");
  if(mockStore.claims.some(c=>c.report_id===report.id&&c.claimant_id===currentUser.id&&["pending","disputed","needs_more_evidence","approved_for_collection","rejected"].includes(c.status)))throw new Error("You already have a claim for this item. Follow the existing review.");
  const types=Array.isArray(body.evidence_types)?body.evidence_types:[];if(!types.length)throw new Error("Choose at least one proof type.");
  const conflict=mockStore.claims.some(c=>c.report_id===report.id&&["pending","disputed","needs_more_evidence"].includes(c.status));
  if(conflict)mockStore.claims.filter(c=>c.report_id===report.id&&["pending","disputed","needs_more_evidence"].includes(c.status)).forEach(c=>c.status="disputed");
  const claim={id:"mock-claim-"+Math.random().toString(36).slice(2,10),report_id:report.id,lost_report_id:body.lost_report_id||null,claimant_id:currentUser.id,claimant_name:currentUser.display_name,claimant_email:currentUser.email,evidence:String(body.evidence||"").trim(),evidence_types:types,status:conflict?"disputed":"pending",appeal_note:null,appeal_count:0,reviewer_note:null,created_at:mockTimestamp(0),updated_at:mockTimestamp(0)};
  mockStore.claims.unshift(claim);mockNotify(MOCK_USERS.office.id,"Claim submitted","A student submitted a claim that needs ownership review.","claim",claim.id,"claim-submitted:"+claim.id);
  return {claim:{id:claim.id,status:claim.status,created_at:claim.created_at},message:"Claim submitted for office review."};
 }
 m=path.match(/^\/api\/claims\/([^/]+)\/(evidence-image|evidence|dispute|decision|handover)$/);
 if(m){
  const id=decodeURIComponent(m[1]),action=m[2],claim=mockStore.claims.find(c=>c.id===id);if(!claim)throw new Error("Claim not found.");const report=mockStore.reports.find(r=>r.id===claim.report_id);
  if(action==="evidence-image"&&method==="POST"){if(currentUser.role!=="student"||claim.claimant_id!==currentUser.id)throw new Error("This is private claim evidence.");const file=body instanceof FormData?body.get("file"):null,data=await mockFileDataUrl(file);if(data)mockStore.evidenceImages[id]=data;return {ok:true,message:"Demo evidence image is held in memory only."};}
  if(action==="evidence-image"&&method==="GET"){if(currentUser.role!=="office"&&claim.claimant_id!==currentUser.id)throw new Error("Evidence image is private.");return {ok:true};}
  if(action==="evidence"&&method==="POST"){if(currentUser.role!=="student"||claim.claimant_id!==currentUser.id)throw new Error("This action is available to the claimant.");if(claim.status!=="needs_more_evidence")throw new Error("The office has not requested additional evidence.");claim.evidence=String(body.evidence||"").trim();claim.status="pending";claim.updated_at=mockTimestamp(0);mockNotify(MOCK_USERS.office.id,"Additional evidence submitted","The claimant added requested evidence.","claim",id,"evidence-added:"+id+":"+claim.updated_at);return {claim:{id,status:claim.status},message:"Additional evidence submitted."};}
  if(action==="dispute"&&method==="POST"){if(currentUser.role!=="student"||claim.claimant_id!==currentUser.id)throw new Error("This action is available to the claimant.");if(claim.status!=="rejected"||Number(claim.appeal_count||0)>=1)throw new Error("This claim is not eligible for another review request.");claim.status="disputed";claim.appeal_note=String(body.reason||"").trim();claim.appeal_count=1;claim.updated_at=mockTimestamp(0);mockNotify(MOCK_USERS.office.id,"Claim decision review requested","A claimant requested a review.","claim",id,"claim-appeal:"+id);return {claim:{id,status:claim.status},message:"Review request submitted."};}
  if(action==="decision"&&method==="POST"){
   mockRequireOffice();if(["rejected","approved_for_collection","returned"].includes(claim.status))throw new Error("This claim has already reached a final review state.");
   if(body.action==="approve"){
    const competitors=mockStore.claims.some(c=>c.id!==id&&c.report_id===claim.report_id&&["pending","disputed","needs_more_evidence"].includes(c.status));if(competitors)throw new Error("Other active claims exist. Resolve competing claims before approving this one.");
    if(report.status!=="available")throw new Error("The item is not available for claim approval.");
    const selected=[...new Set(body.verification_checks||[])],level=Number(report.verification_level||3),min=({1:2,2:3,3:4,4:4})[level]||4;
    if(selected.length<min)throw new Error("Verification level L"+level+" requires at least "+min+" distinct checks.");
    if(!selected.includes("claimant_identity"))throw new Error("Confirm the claimant's identity before approving the claim.");
    if(level>=4&&!selected.includes("authorised_record"))throw new Error("Restricted items require an authorised record/custodian check.");
    claim.verification_checks=selected;claim.status="approved_for_collection";report.status="claim_approved";
   }else if(body.action==="reject")claim.status="rejected";else if(body.action==="request_more_evidence")claim.status="needs_more_evidence";else if(body.action==="mark_disputed")claim.status="disputed";else throw new Error("Unsupported claim decision.");
   claim.reviewer_note=body.note||null;claim.updated_at=mockTimestamp(0);mockNotify(claim.claimant_id,body.action==="approve"?"Claim verified":"Claim review updated",body.action==="approve"?"Your claim passed office verification. Physical handover is still required.":"The office updated the review for your claim.","claim",id,"claim-decision:"+id+":"+claim.status);
   return {claim:{id,status:claim.status},message:"Claim review updated. Physical collection is not recorded by this module."};
  }
  if(action==="handover"&&method==="POST"){
   mockRequireOffice();if(claim.status!=="approved_for_collection")throw new Error("Only an office-verified claim can proceed to handover.");
   if(!body.confirmed_physical_handover||!body.claimant_identity_checked)throw new Error("Confirm identity and physical handover.");
   if(String(body.tag_id||"").trim()!==String(report.tag_id||""))throw new Error("The physical Tag ID does not match the record.");
   claim.status="returned";claim.updated_at=mockTimestamp(0);report.status="returned";report.updated_at=mockTimestamp(0);
   mockStore.ledger.unshift({user_id:claim.claimant_id,points:5,reason:"The reported item was returned to a verified owner",report_id:report.id,created_at:mockTimestamp(0)});
   if(claim.lost_report_id){const lost=mockStore.reports.find(r=>r.id===claim.lost_report_id);if(lost)lost.status="closed";}
   mockNotify(claim.claimant_id,"Item returned","The office recorded the verified return.","claim",id,"mock-return:"+id);return {claim_id:id,status:"returned",message:"Physical handover recorded."};
  }
 }
 if(path==="/api/notifications"&&method==="GET"){const rows=mockStore.notifications.filter(n=>n.user_id===currentUser.id);return {notifications:mockCopy(rows),unread_count:rows.filter(n=>!n.read_at).length};}
 m=path.match(/^\/api\/notifications\/([^/]+)\/read$/);if(m&&method==="POST"){const n=mockStore.notifications.find(x=>x.id===decodeURIComponent(m[1])&&x.user_id===currentUser.id);if(!n)throw new Error("Notification not found.");n.read_at=mockTimestamp(0);return {ok:true};}
 if(path==="/api/notifications/read-all"&&method==="POST"){mockStore.notifications.filter(n=>n.user_id===currentUser.id&&!n.read_at).forEach(n=>n.read_at=mockTimestamp(0));return {ok:true};}
 if(path==="/api/activity/me"&&method==="GET"){
  if(currentUser.role!=="student")throw new Error("Activity rewards are available to student accounts.");
  const entries=mockStore.ledger.filter(x=>x.user_id===currentUser.id),total=entries.reduce((sum,x)=>sum+x.points,0),milestones=[{tier:"Verified Finder",threshold:20,key:"verified-finder"},{tier:"Campus Helper",threshold:50,key:"campus-helper"},{tier:"Community Champion",threshold:100,key:"community-champion"}],next=milestones.find(x=>total<x.threshold)||null;
  return {total_points:total,rules:{verified_intake:10,verified_return:5},ledger:mockCopy(entries),certificates:mockCopy(mockStore.certificates.filter(c=>c.user_id===currentUser.id)),next_milestone:next,points_to_next_milestone:next?next.threshold-total:0,milestones:milestones.map(x=>({...x,earned:total>=x.threshold}))};
 }
 if(path==="/api/leaderboard"&&method==="GET"){
  const sums=[MOCK_USERS.student,MOCK_USERS.student2].map(u=>({...u,total_points:mockStore.ledger.filter(x=>x.user_id===u.id).reduce((sum,x)=>sum+x.points,0),verified_reports:new Set(mockStore.ledger.filter(x=>x.user_id===u.id).map(x=>x.report_id)).size})).filter(x=>x.total_points>0).sort((a,b)=>b.total_points-a.total_points);
  const leaders=sums.map((x,i)=>({rank:i+1,display_name:x.display_name,total_points:x.total_points,verified_reports:x.verified_reports,is_me:x.id===currentUser.id})),self=leaders.find(x=>x.is_me);
  return {leaders:leaders.slice(0,10),my_rank:self?self.rank:null,my_total_points:self?self.total_points:0,participant_count:leaders.length,updated_at:mockTimestamp(0)};
 }
 if(path==="/api/office/summary"&&method==="GET"){mockRequireOffice();const reports=mockStore.reports,claims=mockStore.claims;return {awaiting_intake:reports.filter(x=>x.report_type==="found"&&x.status==="awaiting_intake").length,available_items:reports.filter(x=>x.report_type==="found"&&x.status==="available").length,active_claims:claims.filter(x=>["pending","disputed","needs_more_evidence"].includes(x.status)).length,disputed_claims:claims.filter(x=>x.status==="disputed").length,approved_handover:claims.filter(x=>x.status==="approved_for_collection").length,returned_items:claims.filter(x=>x.status==="returned").length,total_activity_points:mockStore.ledger.reduce((sum,x)=>sum+x.points,0)};}
 throw new Error("This endpoint is not available in the offline preview: "+method+" "+path);
}

async function api(url, options) {
  const opts = Object.assign({ method: "GET", headers: {} }, options || {});
  if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  if (opts.body && !(opts.body instanceof FormData) && !opts.headers["Content-Type"]) {
    opts.headers["Content-Type"] = "application/json";
  }
  if (usingMockApi) return mockApi(url, opts);
  let response;
  try { response = await fetch(url, opts); }
  catch (_) { enableMockMode(); return mockApi(url, opts); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(explainError(data, "Request failed (" + response.status + ")."));
  return data;
}

function showToast(message, error) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", Boolean(error));
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 4800);
}

function showNotice(message, error) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", Boolean(error));
  notice.classList.remove("hidden");
  notice.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function statusLabel(status) {
  return STATUS_LABELS[status] || String(status || "Unknown").replace(/_/g, " ");
}

function statusClass(status) {
  return "status-pill status-" + String(status || "").replace(/[^a-z_]/g, "");
}

function humanDate(value) {
  if (!value) return "Date not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function humanDateTime(value) {
  if (!value) return "Time not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ");
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function categoryLabel(value) {
  const found = (appConfig.categories || []).find((c) => c.value === value);
  return found ? found.label : (value || "Item");
}

async function loadConfig() {
  appConfig = await api("/api/config");
  const categoryOptions = appConfig.categories.map((category) =>
    '<option value="' + escapeHTML(category.value) + '">' + escapeHTML(category.label) + "</option>"
  ).join("");
  $("#reportCategory").innerHTML = '<option value="">Choose a category</option>' + categoryOptions;
  $("#filterCategory").innerHTML = '<option value="">All categories</option>' + categoryOptions;
  const blocks = appConfig.locations.blocks || [];
  const blockOptions = blocks.map((block) =>
    '<option value="' + escapeHTML(block) + '">' + escapeHTML(block) + "</option>"
  ).join("");
  $("#reportBlock").innerHTML = '<option value="">Choose a block or area</option>' + blockOptions;
  $("#filterBlock").innerHTML = '<option value="">All locations</option>' + blockOptions;
  $("#reportFloor").innerHTML = '<option value="">Not sure</option>' + (appConfig.locations.floors || [])
    .map((floor) => '<option value="' + escapeHTML(floor) + '">' + escapeHTML(floor) + "</option>").join("");
  if (appConfig.demo_mode) $("#demoAccess").classList.remove("hidden");
  const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  $("#reportDate").value = localNow.toISOString().slice(0, 16);
}

function showLogin() {
  $("#loginView").classList.remove("hidden");
  $("#appView").classList.add("hidden");
  currentUser = null;
}

function enterApp(user) {
  currentUser = user;
  if (usingMockApi) mockStore.session = mockCopy(user);
  const switchButton = $("#viewSwitchBtn");
  if (switchButton) { switchButton.textContent = user.role === "office" ? "Switch to student" : "Switch to office"; switchButton.classList.toggle("hidden", !usingMockApi && !(appConfig && appConfig.demo_mode)); }
  if ($("#appModeNote")) $("#appModeNote").classList.toggle("hidden", !usingMockApi);
  $("#loginView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#userName").textContent = user.display_name;
  $("#userInitial").textContent = (user.display_name || "U").trim().charAt(0).toUpperCase();
  $("#userInitial").className = "avatar " + (user.role === "office" ? "avatar-office" : "avatar-student");
  $("#roleChip").textContent = user.role === "office" ? "Office staff" : "Student";
  $("#roleChip").className = "role-chip" + (user.role === "office" ? " role-chip-office" : "");
  $("#officeNavButton").classList.toggle("hidden", user.role !== "office");
  $("#activityNavButton").classList.toggle("hidden", user.role === "office");
  $('[data-view="report"], [data-view="my-reports"], [data-view="my-claims"]').forEach((button) => {
    button.classList.toggle("hidden", user.role === "office");
  });
  $("#welcomeTitle").textContent = user.role === "office" ? "Manage found items and claims." : "Find what you are looking for.";
  $("#welcomeSubtitle").textContent = user.role === "office"
    ? "Confirm physical intake and review claims before authorising the next step."
    : "Search office-held items, compare possible matches and submit a private claim.";
  $("#studentNav").classList.remove("hidden");
  navigate(user.role === "office" ? "office" : "browse");
}

function navigate(view) {
  if (!currentUser) return;
  if (view !== "my-reports") selectedLostReportForMatchId = null;
  if (view === "office" && currentUser.role !== "office") view = "browse";
  if (currentUser.role === "office" && ["report", "my-reports", "my-claims", "activity"].includes(view)) view = "office";
  const sections = {
    browse: "#browseView", report: "#reportView", "my-reports": "#myReportsView",
    "my-claims": "#myClaimsView", notifications: "#notificationsView",
    activity: "#activityView", office: "#officeView"
  };
  Object.values(sections).forEach((selector) => $(selector).classList.add("hidden"));
  $(sections[view] || sections.browse).classList.remove("hidden");
  $$("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#notice").classList.add("hidden");
  if (view === "browse") loadBrowse();
  if (view === "my-reports") loadMyReports();
  if (view === "my-claims") loadMyClaims();
  if (view === "office") loadOffice();
  if (view === "notifications") loadNotifications();
  if (view === "activity") loadActivity();
  refreshNotificationBadge();
}

function setReportMode(type) {
  if (!["lost", "found"].includes(type)) return;
  const wasOpen = !$("#reportForm").classList.contains("hidden");
  if (wasOpen && $("#reportType").value && $("#reportType").value !== type) {
    $("#reportForm").reset();
    $("#reportError").textContent = "";
    $("#imageLabel").textContent = "Choose a photo";
    showToast("Switched report type. The previous draft was cleared to avoid mixing Lost and Found details.", false);
  }
  $("#reportType").value = type;
  $("#reportTypeChooser").classList.add("hidden");
  $("#reportForm").classList.remove("hidden");
  $$("[data-report-kind]").forEach((button) => {
    button.classList.toggle("selected", button.dataset.reportKind === type);
    button.setAttribute("aria-pressed", button.dataset.reportKind === type ? "true" : "false");
  });
  if (type === "lost") {
    $("#reportModeTitle").textContent = "Report a lost item";
    $("#reportModeDescription").textContent = "Tell us what went missing. Your report stays in your account and can be compared with items registered by the office.";
    $("#reportFormStepTitle").textContent = "What went missing?";
    $("#reportFormStepHint").textContent = "Describe the item and its last known context.";
    $("#reportDateLabel").textContent = "When did you last see it?";
    $("#reportDateHelp").textContent = "An approximate time helps matching. Leave it blank if you are unsure.";
    $("#reportLocationHeading").textContent = "Where did you last see it?";
    $("#reportLocationHelp").textContent = "Choose the nearest block or nearby place.";
    $("#reportTitle").placeholder = "e.g. Black backpack I lost";
    $("#reportSubmitLabel").textContent = "Submit lost report";
  } else {
    $("#reportModeTitle").textContent = "Report a found item";
    $("#reportModeDescription").textContent = "Record what you found and where. The item only becomes searchable after office staff confirm physical receipt and tagging.";
    $("#reportFormStepTitle").textContent = "What did you find?";
    $("#reportFormStepHint").textContent = "Describe the item without exposing private owner details.";
    $("#reportDateLabel").textContent = "When did you find it?";
    $("#reportDateHelp").textContent = "Use the approximate time you found the item. Office intake time is recorded separately.";
    $("#reportLocationHeading").textContent = "Where did you find it?";
    $("#reportLocationHelp").textContent = "Use the place where you found the item, not its eventual office storage location.";
    $("#reportTitle").placeholder = "e.g. Silver water bottle I found";
    $("#reportSubmitLabel").textContent = "Submit found report";
  }
  if (!$("#reportDate").value) {
    const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    $("#reportDate").value = localNow.toISOString().slice(0, 16);
  }
}

function resetReportMode() {
  $("#reportForm").reset();
  $("#reportForm").classList.add("hidden");
  $("#reportTypeChooser").classList.remove("hidden");
  $("#reportType").value = "";
  $("#reportError").textContent = "";
  $("#imageLabel").textContent = "Choose a photo";
  $("#reportModeTitle").textContent = "Choose your report type";
  $("#reportModeDescription").textContent = "Lost and Found have separate guided paths so each report starts with the right context.";
  $("#reportFormStepTitle").textContent = "Report details";
  $("#reportFormStepHint").textContent = "Add the item and context.";
  $$("[data-report-kind]").forEach((button) => {
    button.classList.remove("selected");
    button.setAttribute("aria-pressed", "false");
  });
}

function evidenceTypeLabel(value) {
  const labels = {
    distinctive_features: "Distinctive features",
    purchase_or_receipt: "Purchase / receipt proof",
    packaging_or_accessory: "Packaging or paired accessory",
    timeline_and_location: "Date and location context",
    device_or_account_context: "Device / account context",
    other: "Other verifiable evidence"
  };
  return labels[value] || value;
}

function buildQuery(formValues) {
  const params = new URLSearchParams();
  Object.keys(formValues).forEach((key) => {
    if (formValues[key] !== undefined && formValues[key] !== null && String(formValues[key]).trim() !== "") {
      params.set(key, String(formValues[key]).trim());
    }
  });
  return params.toString();
}

function itemCard(report, options) {
  const opts = options || {};
  const icon = CATEGORY_ICONS[report.category] || "◌";
  const visual = report.image_url
    ? '<div class="item-visual"><img src="' + escapeHTML(report.image_url) + '" alt="Item photograph" loading="lazy"></div>'
    : '<div class="item-visual"><span class="visual-glyph" aria-hidden="true">' + icon + "</span></div>";
  const claimButton = opts.claim
    ? '<button class="button button-primary button-small" type="button" data-claim="' + escapeHTML(report.id) + '">Submit claim ↗</button>'
    : "";
  const detailsButton = '<button class="button button-quiet button-small" type="button" data-view-details="' + escapeHTML(report.id) + '">View details</button>';
  const characteristics = [
    report.brand ? "Brand: " + report.brand : "",
    report.primary_color ? "Colour: " + report.primary_color : "",
    report.visible_features ? report.visible_features : ""
  ].filter(Boolean);
  const characteristicBlock = characteristics.length
    ? '<div class="characteristic-list">' + characteristics.map((value) => '<span class="characteristic-chip">' + escapeHTML(value) + '</span>').join("") + '</div>'
    : "";
  const reasons = opts.reasons && opts.reasons.length
    ? '<ul class="reason-list">' + opts.reasons.map((reason) => "<li>" + escapeHTML(reason) + "</li>").join("") + "</ul>"
    : "";
  const strength = opts.strength
    ? '<span class="strength-pill strength-' + escapeHTML(opts.strength) + '">' + escapeHTML(opts.strength) + " match</span>"
    : "";
  return '<article class="item-card">' + visual +
    '<div class="item-card-body"><div class="item-topline"><span class="item-ref">' + escapeHTML(report.public_ref) + "</span>" +
    '<span class="category-pill">' + escapeHTML(report.category_label || categoryLabel(report.category)) + "</span></div>" +
    "<h3>" + escapeHTML(report.title) + "</h3>" +
    '<p class="item-description">' + escapeHTML(report.description) + "</p>" +
    characteristicBlock + reasons +
    '<div class="item-meta"><span><b>⌖</b>' + escapeHTML(report.location || "Location not specified") + "</span>" +
    '<span><b>◷</b>' + escapeHTML(humanDate(report.occurred_at)) + "</span></div>" +
    '<div class="item-actions">' + strength + detailsButton + claimButton + "</div></div></article>";
}

async function loadBrowse() {
  if (!currentUser) return;
  const query = buildQuery({
    q: $("#filterQuery").value,
    category: $("#filterCategory").value,
    block: $("#filterBlock").value,
    room: $("#filterRoom") ? $("#filterRoom").value : "",
    date_from: $("#filterDateFrom") ? $("#filterDateFrom").value : "",
    date_to: $("#filterDateTo") ? $("#filterDateTo").value : ""
  });
  try {
    const data = await api("/api/reports" + (query ? "?" + query : ""));
    lastKnownReports = data.reports;
    $("#browseResults").innerHTML = data.reports.map((report) => itemCard(report, { claim: currentUser.role === "student" })).join("");
    $("#browseCount").textContent = data.reports.length + (data.reports.length === 1 ? " item" : " items");
    $("#browseEmpty").classList.toggle("hidden", data.reports.length > 0);
  } catch (error) {
    showToast(error.message, true);
  }
}

function resetSearch() {
  $("#filterQuery").value = "";
  $("#filterCategory").value = "";
  $("#filterBlock").value = "";
  if ($("#filterRoom")) $("#filterRoom").value = "";
  if ($("#filterDateFrom")) $("#filterDateFrom").value = "";
  if ($("#filterDateTo")) $("#filterDateTo").value = "";
  loadBrowse();
}

async function submitReport(event) {
  event.preventDefault();
  $("#reportError").textContent = "";
  const reportType = $("#reportType").value;
  if (!reportType) {
    $("#reportError").textContent = "Choose whether you lost or found the item first.";
    return;
  }
  const body = {
    report_type: reportType,
    title: $("#reportTitle").value.trim(),
    category: $("#reportCategory").value,
    description: $("#reportDescription").value.trim(),
    brand: $("#reportBrand").value.trim() || null,
    primary_color: $("#reportColor").value.trim() || null,
    visible_features: $("#reportFeatures").value.trim() || null,
    occurred_at: $("#reportDate").value || null,
    location_block: $("#reportBlock").value || null,
    location_floor: $("#reportFloor").value || null,
    location_room: $("#reportRoom").value.trim() || null,
    location_area: $("#reportArea").value.trim() || null
  };
  const image = $("#reportImage").files[0];
  if (!body.location_block && !body.location_area) {
    $("#reportError").textContent = "Choose a campus block/building or enter a nearby area.";
    $("#reportArea").focus();
    return;
  }
  if (reportSubmitting) return;
  reportSubmitting = true;
  const submitButton = $('#reportForm button[type="submit"]');
  submitButton.disabled = true;
  try {
    const result = await api("/api/reports", { method: "POST", body });
    let successMessage = result.message;
    let photoFailed = false;
    if (image) {
      const fileBody = new FormData();
      fileBody.append("file", image);
      try {
        await api("/api/reports/" + encodeURIComponent(result.report.id) + "/image", { method: "POST", body: fileBody });
      } catch (uploadError) {
        photoFailed = true;
        successMessage += " The report was saved, but the photo upload failed: " + uploadError.message;
      }
    }
    resetReportMode();
    navigate("my-reports");
    showToast(successMessage, photoFailed);
  } catch (error) {
    $("#reportError").textContent = error.message;
  } finally {
    reportSubmitting = false;
    submitButton.disabled = false;
  }
}

async function loadMyReports() {
  if (!currentUser || currentUser.role !== "student") return;
  $("#matchesPanel").classList.add("hidden");
  try {
    const data = await api("/api/reports?mine=true");
    $("#myReportsList").innerHTML = data.reports.map((report) => {
      const matchButton = report.report_type === "lost" && report.status === "open"
        ? '<button class="button button-primary button-small" type="button" data-matches="' + escapeHTML(report.id) + '">Find possible matches</button>'
        : "";
      const canClose = (report.report_type === "lost" && report.status === "open" && !report.has_active_linked_claim) ||
        (report.report_type === "found" && report.status === "awaiting_intake");
      const closeButton = canClose
        ? '<button class="button button-quiet button-small" type="button" data-close-report="' + escapeHTML(report.id) +
          '" data-close-type="' + escapeHTML(report.report_type) + '">' +
          (report.report_type === "found" ? "Withdraw report" : "Close report") + '</button>'
        : "";
      const linkedClaimNote = report.report_type === "lost" && report.status === "open" && report.has_active_linked_claim
        ? '<p class="field-hint">This lost report is linked to a claim under review. Resolve the claim before closing the report.</p>'
        : "";
      const type = report.report_type === "lost" ? "Lost report" : "Found report";
      const imageNote = report.report_type === "found" && report.status === "awaiting_intake"
        ? "The office must confirm physical receipt before the item can appear in search."
        : "";
      const characteristics = [
        report.brand ? "Brand: " + report.brand : "",
        report.primary_color ? "Colour: " + report.primary_color : "",
        report.visible_features || ""
      ].filter(Boolean);
      const extra = characteristics.length
        ? '<div class="characteristic-list">' + characteristics.map((value) => '<span class="characteristic-chip">' + escapeHTML(value) + '</span>').join("") + '</div>'
        : "";
      return '<article class="list-card"><div class="list-card-head"><div><h3>' + escapeHTML(report.title) + '</h3><p>' +
        escapeHTML(type + " · " + report.public_ref) + "</p></div><span class=\"" + statusClass(report.status) + "\">" +
        escapeHTML(statusLabel(report.status)) + "</span></div><p>" + escapeHTML(report.description) + "</p>" + extra +
        '<div class="list-card-meta"><span>⌖ ' + escapeHTML(report.location) + "</span><span>◷ " + escapeHTML(humanDate(report.occurred_at)) + "</span></div>" +
        (imageNote ? '<p class="field-hint">' + escapeHTML(imageNote) + "</p>" : "") +
        linkedClaimNote +
        '<div class="card-actions">' + matchButton + closeButton + "</div></article>";
    }).join("");
    $("#myReportsEmpty").classList.toggle("hidden", data.reports.length > 0);
  } catch (error) { showToast(error.message, true); }
}

async function loadMatches(reportId) {
  selectedLostReportForMatchId = reportId;
  $("#matchesPanel").classList.remove("hidden");
  $("#matchResults").innerHTML = '<div class="list-card"><p>Comparing report details…</p></div>';
  try {
    const result = await api("/api/reports/" + encodeURIComponent(reportId) + "/matches");
    const detailedMatches = result.matches.map((match) => ({
      ...match.report, match_strength: match.strength, match_reasons: match.reasons || []
    }));
    lastKnownReports = lastKnownReports.filter((report) => !detailedMatches.some((match) => match.id === report.id)).concat(detailedMatches);
    $("#matchResults").innerHTML = detailedMatches.map((report) => itemCard(report, {
      claim: true, strength: report.match_strength, reasons: report.match_reasons
    })).join("");
    if (!result.matches.length) {
      $("#matchResults").innerHTML = '<div class="empty-state"><span class="empty-icon">⌕</span><h3>No available matches yet</h3><p>Your report remains active. Try checking again after new found-item reports are received by the office.</p></div>';
    }
    $("#matchesPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { showToast(error.message, true); }
}

async function loadMyClaims() {
  if (!currentUser || currentUser.role !== "student") return;
  try {
    const data = await api("/api/claims");
    const activeCount = data.claims.filter((claim) => ["pending", "disputed", "needs_more_evidence"].includes(claim.status)).length;
    $("#claimNavCount").textContent = String(activeCount);
    $("#claimNavCount").classList.toggle("hidden", activeCount === 0);
    $("#myClaimsList").innerHTML = data.claims.map((claim) => {
      let guidance = "Your claim is awaiting review by authorised office staff.";
      if (claim.status === "disputed") guidance = claim.appeal_note
        ? "You requested a review of the earlier decision. The office must review the dispute before the claim can proceed."
        : "Competing claims exist. The item is on hold until authorised office staff resolve the competing claims.";
      if (claim.status === "needs_more_evidence") guidance = "The office has requested additional evidence. Add relevant details without sharing passwords, PINs or one-time codes.";
      if (claim.status === "approved_for_collection") guidance = "Your claim has been verified. The item is not marked returned until campus staff confirm physical handover.";
      if (claim.status === "returned") guidance = "The office recorded the return of the item. This claim is complete.";
      if (claim.status === "rejected") guidance = Number(claim.appeal_count || 0) < 1
        ? "This claim was not approved. You can request one review by explaining what evidence may have been overlooked."
        : "This claim was not approved after review. No further review request is available in this prototype; contact the campus office if needed.";
      const addEvidence = claim.status === "needs_more_evidence"
        ? '<button class="button button-primary button-small" type="button" data-add-evidence="' + escapeHTML(claim.id) + '">Add evidence</button>'
        : "";
      const disputeForm = claim.status === "rejected" && Number(claim.appeal_count || 0) < 1
        ? '<div class="claim-dispute-form"><label>Why should this decision be reviewed?<textarea data-dispute-reason="' + escapeHTML(claim.id) + '" rows="3" minlength="20" maxlength="1000" placeholder="Explain which evidence or detail should be reconsidered (at least 20 characters)."></textarea></label><button class="button button-quiet button-small" type="button" data-dispute-claim="' + escapeHTML(claim.id) + '">Request review</button></div>'
        : "";
      const appealNote = claim.appeal_note
        ? '<div class="claim-appeal-note"><strong>Your review request</strong><p>' + escapeHTML(claim.appeal_note) + '</p></div>'
        : "";
      const linkedLost = claim.linked_lost_report
        ? '<div class="linked-report-line"><strong>Linked lost report</strong><span>' +
          escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
          '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
          escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
        : "";
      const evidenceTypes = Array.isArray(claim.evidence_types) ? claim.evidence_types : [];
      const evidenceChips = evidenceTypes.length
        ? '<div class="evidence-type-list"><strong>Proof types</strong>' +
          evidenceTypes.map((type) => '<span class="characteristic-chip">' + escapeHTML(evidenceTypeLabel(type)) + '</span>').join("") + '</div>'
        : "";
      const evidencePhoto = claim.evidence_image_available
        ? '<figure class="evidence-image-preview"><img src="/api/claims/' + escapeHTML(claim.id) + '/evidence-image" alt="Your private evidence preview" draggable="false"><figcaption>Private, watermarked preview</figcaption></figure>'
        : "";
      return '<article class="list-card" data-claim-card="' + escapeHTML(claim.id) + '" data-verification-level="' + levelNumber + '" data-minimum-checks="' + minimumChecks + '"><div class="list-card-head"><div><h3>' + escapeHTML(claim.report.title) + '</h3><p>' +
        escapeHTML(claim.report.public_ref + " · Submitted " + humanDate(claim.created_at)) + "</p></div><span class=\"" + statusClass(claim.status) + "\">" +
        escapeHTML(statusLabel(claim.status)) + "</span></div><p>" + escapeHTML(guidance) + '</p>' + appealNote + linkedLost + '<div class="list-card-meta"><span>⌖ ' +
        escapeHTML(claim.report.location) + "</span><span>Reference " + escapeHTML(claim.report.public_ref) + "</span></div>" +
        evidenceChips + evidencePhoto + '<div class="card-actions">' + addEvidence + "</div>" + disputeForm + "</article>";
    }).join("");
    $("#myClaimsEmpty").classList.toggle("hidden", data.claims.length > 0);
  } catch (error) { showToast(error.message, true); }
}

async function openItemDetails(reportId) {
  let report = findReportById(reportId);
  if (!report) {
    showToast("Item details are not loaded yet. Refresh the search or reopen the match list.", true);
    return;
  }
  selectedDetailsReportId = report.id;
  $("#itemDetailsTitle").textContent = report.title || "Item details";
  const facts = [
    ["Reference", report.public_ref],
    ["Category", report.category_label || categoryLabel(report.category)],
    ["Status", statusLabel(report.status)],
    ["Location", report.location || "Not specified"],
    ["Approximate date", humanDateTime(report.occurred_at)],
    ["Brand / make", report.brand],
    ["Main colour", report.primary_color],
    ["Visible characteristics", report.visible_features],
    ["Record updated", humanDateTime(report.updated_at)]
  ].filter((fact) => fact[1]);
  const photo = report.image_url
    ? '<div class="item-detail-photo-wrap"><img class="item-detail-photo" src="' + escapeHTML(report.image_url) + '" alt="Watermarked item preview" draggable="false"><small>Watermarked preview · public item details only</small></div>'
    : "";
  const matchDetails = report.match_reasons && report.match_reasons.length
    ? '<section class="match-detail-block"><h3>Why it was suggested</h3><p class="muted">These are comparison signals, not proof of ownership.</p><ul class="reason-list">' +
      report.match_reasons.map((reason) => "<li>" + escapeHTML(reason) + "</li>").join("") + '</ul><span class="strength-pill strength-' + escapeHTML(report.match_strength || "moderate") + '">' +
      escapeHTML(report.match_strength || "Possible") + " match</span></section>"
    : "";
  $("#itemDetailsContent").innerHTML = photo + '<p class="item-detail-description">' + escapeHTML(report.description || "") + '</p><dl class="item-detail-grid">' +
    facts.map(([key, value]) => '<div><dt>' + escapeHTML(key) + '</dt><dd>' + escapeHTML(value) + '</dd></div>').join("") +
    '</dl>' + matchDetails + '<p class="field-hint">Keep hidden marks, serial numbers and access codes private. Ownership is verified separately by office staff.</p>';
  const canClaim = currentUser && currentUser.role === "student" && report.report_type === "found" && report.status === "available";
  $("#itemDetailsClaimButton").classList.toggle("hidden", !canClaim);
  $("#itemDetailsDialog").showModal();
}

function openClaim(reportId) {
  const report = findReportById(reportId);
  if (!report) {
    // The report can come from a match card not currently stored in the browse response.
    loadClaimReport(reportId);
    return;
  }
  selectedClaimReport = report;
  showClaimDialog(report);
}

let lastKnownReports = [];
let selectedDetailsReportId = null;
function findReportById(id) {
  return lastKnownReports.find((report) => report.id === id) || null;
}

async function loadClaimReport(reportId) {
  try {
    const data = await api("/api/reports?q=" + encodeURIComponent(reportId));
    const report = data.reports.find((item) => item.id === reportId);
    if (!report) throw new Error("That item is no longer available to claim. Refresh the list.");
    selectedClaimReport = report;
    showClaimDialog(report);
  } catch (error) { showToast(error.message, true); }
}

function showClaimDialog(report) {
  $("#claimError").textContent = "";
  $("#claimItemSummary").innerHTML = "<strong>" + escapeHTML(report.title) + " · " + escapeHTML(report.public_ref) +
    "</strong><small>" + escapeHTML(categoryLabel(report.category)) + " · " + escapeHTML(report.location) + "</small>";
  $("#claimEvidence").value = "";
  $$('input[name="claimEvidenceType"]').forEach((input) => { input.checked = false; });
  $("#claimEvidenceImage").value = "";
  $("#claimEvidenceImageLabel").textContent = "Attach one supporting photo (optional)";
  const preferredLostReportId = selectedLostReportForMatchId;
  selectedLostReportForMatchId = null;
  $("#claimSubmitButton").disabled = true;
  $("#claimDialog").showModal();
  loadClaimLostReports(preferredLostReportId);
}

async function loadClaimLostReports(preferredReportId) {
  const select = $("#claimLostReport");
  const requestId = ++lostReportOptionsRequest;
  select.disabled = true;
  select.innerHTML = '<option value="">Loading your open lost reports…</option>';
  try {
    const data = await api("/api/reports?mine=true&report_type=lost");
    if (requestId !== lostReportOptionsRequest) return;
    const openReports = data.reports.filter((item) => item.report_type === "lost" && item.status === "open");
    select.innerHTML = '<option value="">No linked lost report</option>' + openReports.map((item) =>
      '<option value="' + escapeHTML(item.id) + '">' + escapeHTML(item.title + " · " + item.public_ref + " · " + humanDate(item.occurred_at)) + '</option>'
    ).join("");
    if (preferredReportId && openReports.some((item) => item.id === preferredReportId)) {
      select.value = preferredReportId;
    }
    if (!openReports.length) {
      select.innerHTML = '<option value="">No open lost reports to link</option>';
    }
    select.disabled = false;
    $("#claimSubmitButton").disabled = false;
  } catch (error) {
    if (requestId !== lostReportOptionsRequest) return;
    select.innerHTML = '<option value="">Continue without linking a lost report</option>';
    select.disabled = false;
    $("#claimSubmitButton").disabled = false;
    showToast("Could not load your open lost reports. You can still submit the claim without linking one.", true);
  }
}

async function submitClaim(event) {
  event.preventDefault();
  if (!selectedClaimReport || claimSubmitting) return;
  $("#claimError").textContent = "";
  const evidenceTypes = $$('input[name="claimEvidenceType"]:checked').map((input) => input.value);
  if (!evidenceTypes.length) {
    $("#claimError").textContent = "Select at least one kind of evidence before submitting.";
    return;
  }
  const evidenceImage = $("#claimEvidenceImage").files[0];
  claimSubmitting = true;
  $("#claimSubmitButton").disabled = true;
  try {
    const result = await api("/api/claims", {
      method: "POST",
      body: {
        report_id: selectedClaimReport.id,
        lost_report_id: $("#claimLostReport").value || null,
        evidence: $("#claimEvidence").value.trim(),
        evidence_types: evidenceTypes
      }
    });
    let resultMessage = result.message + " Your evidence is private.";
    let imageFailed = false;
    if (evidenceImage) {
      const fileBody = new FormData();
      fileBody.append("file", evidenceImage);
      try {
        await api("/api/claims/" + encodeURIComponent(result.claim.id) + "/evidence-image", { method: "POST", body: fileBody });
        resultMessage += " The supporting image was attached.";
      } catch (uploadError) {
        imageFailed = true;
        resultMessage += " The text claim was saved, but the photo was rejected: " + uploadError.message;
      }
    }
    $("#claimDialog").close();
    showToast(resultMessage, imageFailed);
    navigate("my-claims");
  } catch (error) {
    $("#claimError").textContent = error.message;
  } finally {
    claimSubmitting = false;
    $("#claimSubmitButton").disabled = false;
  }
}

function openAdditionalEvidence(claimId) {
  selectedEvidenceClaimId = claimId;
  const card = document.querySelector('[data-claim-card="' + CSS.escape(claimId) + '"]');
  const itemTitle = card ? card.querySelector("h3").textContent : "this item";
  $("#additionalEvidenceSummary").textContent = "Add the evidence requested for " + itemTitle + ". This response is private to you and authorised office reviewers.";
  $("#additionalEvidenceText").value = "";
  $("#additionalEvidenceError").textContent = "";
  $("#saveAdditionalEvidenceButton").disabled = false;
  $("#additionalEvidenceDialog").showModal();
}

async function submitAdditionalEvidence(event) {
  event.preventDefault();
  if (!selectedEvidenceClaimId) return;
  const evidence = $("#additionalEvidenceText").value.trim();
  if (evidence.length < 20) {
    $("#additionalEvidenceError").textContent = "Please provide at least 20 characters of relevant evidence.";
    $("#additionalEvidenceText").focus();
    return;
  }
  $("#additionalEvidenceError").textContent = "";
  $("#saveAdditionalEvidenceButton").disabled = true;
  try {
    const result = await api("/api/claims/" + encodeURIComponent(selectedEvidenceClaimId) + "/evidence", {
      method: "POST", body: { evidence }
    });
    $("#additionalEvidenceDialog").close();
    selectedEvidenceClaimId = null;
    showToast(result.claim.message, false);
    await loadMyClaims();
  } catch (error) {
    $("#additionalEvidenceError").textContent = error.message;
  } finally {
    $("#saveAdditionalEvidenceButton").disabled = false;
  }
}

async function loadOffice() {
  if (!currentUser || currentUser.role !== "office") return;
  try {
    const [summary, queueData, claimData, inventoryData] = await Promise.all([
      api("/api/office/summary"),
      api("/api/reports?report_type=found&status=awaiting_intake"),
      api("/api/claims"),
      api("/api/reports?report_type=found")
    ]);
    $("#officeStats").innerHTML = [
      ["Awaiting intake", summary.awaiting_intake],
      ["Items available", summary.available_items],
      ["Active claims", summary.active_claims],
      ["Disputed claims", summary.disputed_claims],
      ["Ready for handover", summary.approved_handover || 0],
      ["Items returned", summary.returned_items || 0]
    ].map((stat) => '<div class="stat-card"><span>' + escapeHTML(stat[0]) + '</span><strong>' + escapeHTML(stat[1]) + "</strong></div>").join("");
    const queue = queueData.reports.filter((report) => report.status === "awaiting_intake");
    $("#intakeQueue").innerHTML = queue.map((report) => intakeCard(report)).join("");
    $("#intakeEmpty").classList.toggle("hidden", queue.length > 0);
    const inventory = inventoryData.reports.filter((report) => ["available", "claim_approved"].includes(report.status) && report.tag_id);
    $("#officeInventory").innerHTML = inventory.map((report) => officeInventoryCard(report)).join("");
    $("#officeInventoryEmpty").classList.toggle("hidden", inventory.length > 0);
    const active = claimData.claims.filter((claim) => ["pending", "disputed", "needs_more_evidence"].includes(claim.status));
    $("#officeClaims").innerHTML = active.map((claim) => officeClaimCard(claim)).join("");
    $("#officeClaimsEmpty").classList.toggle("hidden", active.length > 0);
    const handovers = claimData.claims.filter((claim) => claim.status === "approved_for_collection");
    $("#handoverQueue").innerHTML = handovers.map((claim) => officeHandoverCard(claim)).join("");
    $("#handoverEmpty").classList.toggle("hidden", handovers.length > 0);
    refreshNotificationBadge();
  } catch (error) { showToast(error.message, true); }
}

function officeInventoryCard(report) {
  return '<article class="list-card"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title + " · " + report.public_ref) + '</h3><p>' +
    escapeHTML(statusLabel(report.status)) + '</p></div><span class="status-pill status-available">In campus custody</span></div>' +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id) +
    '</span><span>Stored at: ' + escapeHTML(report.storage_location || "Location needs confirmation") + '</span>' +
    '<span>Last updated: ' + escapeHTML(humanDateTime(report.updated_at)) + '</span></div>' +
    '<div class="card-actions"><button class="button button-quiet button-small" type="button" data-storage-update="' +
    escapeHTML(report.id) + '" data-current-location="' + escapeHTML(report.storage_location || "") +
    '">Update storage location</button></div></article>';
}

function officeHandoverCard(claim) {
  const report = claim.report;
  const linkedLostMeta = claim.linked_lost_report
    ? '<div class="linked-report-line office-linked-report"><strong>Linked lost report</strong><span>' +
      escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
      '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
      escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
    : "";
  return '<article class="list-card"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title + " · " + report.public_ref) + '</h3><p>Claimant: ' +
    escapeHTML(claim.claimant_name) + " · " + escapeHTML(claim.claimant_email) +
    "</p></div><span class=\"" + statusClass(claim.status) + "\">Verified claim</span></div>" +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id || "Not assigned") +
    "</span><span>Verification level: " + escapeHTML(report.verification_level ? "L" + report.verification_level : "Not assigned") +
    "</span><span>Stored at: " + escapeHTML(report.storage_location || "Location needs confirmation") + "</span></div>" + linkedLostMeta + "<p>Before release, compare the physical item with the tag and verify the claimant under campus policy.</p>" +
    '<div class="card-actions"><button class="button button-primary button-small" type="button" data-handover="' +
    escapeHTML(claim.id) + '" data-tag="' + escapeHTML(report.tag_id || "") + '">Confirm physical handover</button></div></article>';
}

function intakeCard(report) {
  return '<article class="list-card"><div class="list-card-head"><div><h3>' + escapeHTML(report.title) + '</h3><p>' +
    escapeHTML(report.public_ref + " · Reported " + humanDate(report.created_at)) + "</p></div><span class=\"" + statusClass(report.status) + "\">Awaiting intake</span></div>" +
    "<p>" + escapeHTML(report.description) + "</p><div class=\"list-card-meta\"><span>⌖ " + escapeHTML(report.location) +
    "</span><span>" + escapeHTML(categoryLabel(report.category)) + "</span></div>" +
    '<form class="intake-form" data-intake-form="' + escapeHTML(report.id) + '">' +
    '<label class="wide">Campus storage location<input name="storage_location" required minlength="4" maxlength="160" placeholder="Lost & Found room · cabinet A · shelf 01"></label>' +
    '<label class="wide">Private identifying detail / approved verification method<textarea name="private_detail" maxlength="1200" placeholder="Not shown to students. For restricted items, describe the authorised verification method without copying unnecessary sensitive data."></textarea></label>' +
    '<label>Estimated value band<select name="value_band"><option value="unknown">Unknown</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>' +
    '<label>Sensitivity level<select name="sensitivity_level"><option value="1">1 · Routine</option><option value="2">2 · Elevated</option><option value="3">3 · Sensitive</option><option value="4">4 · Restricted</option></select></label>' +
    '<label class="checkbox-line wide"><input type="checkbox" name="confirmed_physical_receipt" required> I confirm the physical item is in campus office custody and has been placed at the recorded storage location.</label>' +
    '<div class="wide"><button class="button button-primary button-small" type="submit">Confirm receipt, store & assign tag</button></div></form></article>';
}

function officeClaimCard(claim) {
  const report = claim.report;
  const levelNumber = Number(report.verification_level || 3);
  const level = "L" + levelNumber;
  const minimumChecks = ({ 1: 2, 2: 3, 3: 4, 4: 4 })[levelNumber] || 4;
  const privateDetail = report.private_verification_detail || "No private verification detail recorded.";
  const checks = [
    ["distinctive_features", "Distinctive features / owner-only detail match"],
    ["date_location", "Date and location are consistent"],
    ["physical_inspection", "Physical item inspected"],
    ["supporting_evidence", "Independent supporting evidence reviewed"],
    ["owner_specific_detail", "Owner-specific detail checked"],
    ["claimant_identity", "Claimant identity checked"]
  ];
  if (levelNumber >= 4) checks.push(["authorised_record", "Authorised record / custodian checked"]);
  const checklist = '<div class="verification-checklist"><div class="verification-checklist-heading"><strong>Verification checklist</strong><span>' +
    escapeHTML("Level " + levelNumber + " · minimum " + minimumChecks + " checks") +
    '</span></div><p class="field-hint">Check the evidence you actually reviewed. Claimant identity is always required; restricted items also require an authorised-record check.</p>' +
    '<div class="verification-check-grid">' + checks.map(([value, label]) =>
      '<label class="verify-check"><input type="checkbox" data-verification-check="true" value="' + escapeHTML(value) + '"><span>' + escapeHTML(label) + '</span></label>'
    ).join("") + '</div></div>';
  const actions = '<div class="decision-note"><input type="text" maxlength="800" data-note-for="' + escapeHTML(claim.id) +
    '" placeholder="Internal review note (optional)"></div><div class="card-actions">' +
    '<button class="button button-primary button-small" type="button" data-decision="approve" data-claim-id="' + escapeHTML(claim.id) + '">Verify claim</button>' +
    '<button class="button button-amber button-small" type="button" data-decision="request_more_evidence" data-claim-id="' + escapeHTML(claim.id) + '">Request evidence</button>' +
    '<button class="button button-danger button-small" type="button" data-decision="mark_disputed" data-claim-id="' + escapeHTML(claim.id) + '">Mark disputed</button>' +
    '<button class="button button-quiet button-small" type="button" data-decision="reject" data-claim-id="' + escapeHTML(claim.id) + '">Reject claim</button></div>';
  const linkedLost = claim.linked_lost_report
    ? '<div class="linked-report-line office-linked-report"><strong>Linked lost report</strong><span>' +
      escapeHTML(claim.linked_lost_report.title + " · " + claim.linked_lost_report.public_ref) +
      '</span><span class="' + statusClass(claim.linked_lost_report.status) + '">' +
      escapeHTML(statusLabel(claim.linked_lost_report.status)) + '</span></div>'
    : "";
  const evidenceTypes = Array.isArray(claim.evidence_types) ? claim.evidence_types : [];
  const evidenceChips = evidenceTypes.length
    ? '<div class="evidence-type-list"><strong>CLAIMANT-PROVIDED PROOF TYPES</strong>' +
      evidenceTypes.map((type) => '<span class="characteristic-chip">' + escapeHTML(evidenceTypeLabel(type)) + '</span>').join("") + '</div>'
    : "";
  const evidenceImageSource = usingMockApi && mockStore.evidenceImages[claim.id] ? mockStore.evidenceImages[claim.id] : "/api/claims/" + escapeHTML(claim.id) + "/evidence-image";
  const evidencePhoto = claim.evidence_image_available
    ? '<figure class="evidence-image-preview"><img src="' + evidenceImageSource + '" alt="Private claim evidence preview" draggable="false"><figcaption>Private preview · claimant and office only</figcaption></figure>'
    : "";
  return '<article class="list-card" data-claim-card="' + escapeHTML(claim.id) + '"><div class="list-card-head"><div><h3>' +
    escapeHTML(report.title) + " · " + escapeHTML(report.public_ref) +
    '</h3><p>Claimant: ' + escapeHTML(claim.claimant_name) + " · " + escapeHTML(claim.claimant_email) + "</p></div><span class=\"" + statusClass(claim.status) +
    "\">" + escapeHTML(statusLabel(claim.status)) + "</span></div>" +
    '<div class="internal-meta"><span>Physical tag: ' + escapeHTML(report.tag_id || "Not assigned") + "</span><span>Verification: " + escapeHTML(level) +
    "</span><span>Value band: " + escapeHTML(report.value_band || "unknown") + "</span><span>Sensitivity: " + escapeHTML(report.sensitivity_level) + "</span></div>" +
    linkedLost +
    '<div class="claim-evidence"><strong>CLAIMANT EVIDENCE · PRIVATE</strong><p>' + escapeHTML(claim.evidence) + "</p></div>" +
    evidenceChips + evidencePhoto +
    (claim.appeal_note ? '<div class="claim-appeal-note"><strong>CLAIMANT REVIEW REQUEST</strong><p>' + escapeHTML(claim.appeal_note) + '</p></div>' : "") +
    '<div class="internal-detail"><strong>INTERNAL VERIFICATION DETAIL</strong><small>' + escapeHTML(privateDetail) + "</small></div>" +
    '<div class="list-card-meta"><span>⌖ ' + escapeHTML(report.location) + "</span><span>Submitted " + escapeHTML(humanDateTime(claim.created_at)) + "</span></div>" +
    (claim.status === "disputed" ? '<p class="field-hint">' + escapeHTML(claim.appeal_note
      ? "This is a claimant-requested review of a previous rejection. Review the appeal note and evidence again."
      : "Resolve all competing active claims before approving any one claim.") + '</p>' : "") +
    checklist + actions + "</article>";
}

async function submitIntake(event) {
  event.preventDefault();
  const form = event.target;
  if (!form.matches("[data-intake-form]")) return;
  const values = new FormData(form);
  const body = {
    confirmed_physical_receipt: values.get("confirmed_physical_receipt") === "on",
    storage_location: String(values.get("storage_location") || "").trim(),
    private_detail: String(values.get("private_detail") || "").trim() || null,
    value_band: values.get("value_band"),
    sensitivity_level: Number(values.get("sensitivity_level"))
  };
  try {
    const result = await api("/api/reports/" + encodeURIComponent(form.dataset.intakeForm) + "/intake", { method: "POST", body });
    showToast("Item received, tagged and stored at " + result.report.storage_location + " · " + result.report.tag_id, false);
    loadOffice();
  } catch (error) { showToast(error.message, true); }
}



async function refreshNotificationBadge() {
  if (!currentUser) return;
  try {
    const data = await api("/api/notifications");
    const badge = $("#notificationNavCount");
    badge.textContent = String(data.unread_count || 0);
    badge.classList.toggle("hidden", !data.unread_count);
  } catch (_) {}
}

async function loadNotifications() {
  if (!currentUser) return;
  try {
    const data = await api("/api/notifications");
    $("#notificationNavCount").textContent = String(data.unread_count || 0);
    $("#notificationNavCount").classList.toggle("hidden", !data.unread_count);
    $("#notificationsList").innerHTML = data.notifications.map((item) => {
      const canViewMatches = item.entity_type === "report" && item.entity_id &&
        String(item.title || "").toLowerCase().includes("possible item match");
      const matchButton = canViewMatches
        ? '<button class="button button-primary button-small" type="button" data-notification-matches="' + escapeHTML(item.entity_id) + '">View match details</button>'
        : "";
      return '<article class="notification-card ' + (item.read_at ? "is-read" : "is-unread") + '">' +
        '<div class="notification-mark">' + (item.read_at ? "✓" : "•") + '</div><div class="notification-content"><div class="notification-heading"><strong>' +
        escapeHTML(item.title) + '</strong><span>' + escapeHTML(humanDateTime(item.created_at)) + '</span></div><p>' +
        escapeHTML(item.message) + '</p><div class="notification-actions">' + matchButton + (!item.read_at
          ? '<button class="button button-quiet button-small" type="button" data-notification-read="' + escapeHTML(item.id) + '">Mark read</button>'
          : "") + '</div></div></article>';
    }).join("");
    $("#notificationsEmpty").classList.toggle("hidden", data.notifications.length > 0);
  } catch (error) { showToast(error.message, true); }
}

async function markNotificationRead(notificationId) {
  try {
    await api("/api/notifications/" + encodeURIComponent(notificationId) + "/read", { method: "POST" });
    await loadNotifications();
  } catch (error) { showToast(error.message, true); }
}

async function markAllNotificationsRead() {
  try {
    await api("/api/notifications/read-all", { method: "POST" });
    await loadNotifications();
    showToast("Notifications marked as read.", false);
  } catch (error) { showToast(error.message, true); }
}

async function loadActivity() {
  if (!currentUser || currentUser.role !== "student") return;
  try {
    const data = await api("/api/activity/me");
    const total = Number(data.total_points || 0);
    const next = data.next_milestone;
    const progress = next ? Math.min(100, total / next.threshold * 100) : 100;
    const nextText = next
      ? (data.points_to_next_milestone + " more points to " + next.tier)
      : "All current recognition milestones earned";
    $("#activityOverview").innerHTML =
      '<div class="activity-points-card"><div><p class="eyebrow">VERIFIED ACTIVITY</p><strong>' + escapeHTML(total) +
      '</strong><span>total points</span></div><div class="points-symbol">✦</div><p class="muted">Points are awarded for contributions verified by the campus office.</p></div>' +
      '<div class="milestone-card"><div class="milestone-heading"><div><p class="eyebrow">NEXT MILESTONE</p><h3>' +
      escapeHTML(next ? next.tier : "Recognition complete") + '</h3></div><span class="count-pill">' +
      escapeHTML(next ? (next.threshold + " pts") : "Complete") + "</span></div><div class=\"progress-track\"><span style=\"width:" +
      progress + '%"></span></div><p class="muted">' + escapeHTML(nextText) + '</p><div class="point-rules"><span>+' +
      escapeHTML(data.rules.verified_intake) + ' <small>verified office intake</small></span><span>+' +
      escapeHTML(data.rules.verified_return) + ' <small>verified return</small></span></div></div>';
    const leaderboard = await api("/api/leaderboard");
    $("#leaderboardParticipantCount").textContent = leaderboard.participant_count + (leaderboard.participant_count === 1 ? " contributor" : " contributors");
    $("#leaderboardSummary").innerHTML = leaderboard.my_rank
      ? '<div class="leaderboard-self"><span>Your current rank</span><strong>#' + escapeHTML(leaderboard.my_rank) + '</strong><small>' + escapeHTML(leaderboard.my_total_points) + ' verified points</small></div>'
      : '<div class="leaderboard-self"><span>Your current rank</span><strong>—</strong><small>Earn points when the office verifies a contribution.</small></div>';
    $("#leaderboardList").innerHTML = leaderboard.leaders.map((leader) =>
      '<div class="leaderboard-row ' + (leader.is_me ? "leaderboard-row-self" : "") + '"><span class="leaderboard-rank">#' +
      escapeHTML(leader.rank) + '</span><span class="leaderboard-name">' + escapeHTML(leader.display_name) + '</span><span class="leaderboard-detail">' +
      escapeHTML(leader.verified_reports) + ' reports</span><strong class="leaderboard-points">' + escapeHTML(leader.total_points) + ' pts</strong></div>'
    ).join("");
    $("#leaderboardEmpty").classList.toggle("hidden", leaderboard.leaders.length > 0);
    $("#certificateList").innerHTML = data.certificates.map((certificate) =>
      '<article class="certificate-card"><div class="certificate-emblem">✧</div><div class="certificate-copy"><span class="item-ref">' +
      escapeHTML(certificate.serial) + "</span><h3>" + escapeHTML(certificate.tier) + '</h3><p class="muted">' +
      escapeHTML(certificate.points_at_issue + " points at issue · " + humanDate(certificate.issued_at)) + '</p></div><button class="button button-primary button-small" type="button" data-certificate-download="' +
      escapeHTML(certificate.id) + '">Download PDF ↗</button></article>'
    ).join("");
    $("#certificateEmpty").classList.toggle("hidden", data.certificates.length > 0);
    $("#activityLedger").innerHTML = data.ledger.map((entry) =>
      '<article class="ledger-row"><div class="ledger-icon">＋</div><div class="ledger-copy"><strong>' +
      escapeHTML(entry.reason) + '</strong><small>' + escapeHTML(humanDateTime(entry.created_at)) +
      (entry.report_id ? " · Verified report recorded" : "") + '</small></div><span class="ledger-points">+' +
      escapeHTML(entry.points) + " pts</span></article>"
    ).join("");
    $("#activityEmpty").classList.toggle("hidden", data.ledger.length > 0);
  } catch (error) { showToast(error.message, true); }
}

function openStorageUpdate(reportId, currentLocation, itemTitle) {
  selectedStorageReportId = reportId;
  $("#storageUpdateSummary").textContent = itemTitle + ". Update this record only after the item has physically been moved.";
  $("#storageUpdateLocation").value = currentLocation || "";
  $("#storageUpdateNote").value = "";
  $("#storageUpdateError").textContent = "";
  $("#saveStorageUpdateButton").disabled = false;
  $("#storageUpdateDialog").showModal();
}

async function submitStorageLocation(event) {
  event.preventDefault();
  if (!selectedStorageReportId) return;
  const storageLocation = $("#storageUpdateLocation").value.trim();
  if (storageLocation.length < 4) {
    $("#storageUpdateError").textContent = "Enter a specific room, cabinet, shelf or storage area.";
    $("#storageUpdateLocation").focus();
    return;
  }
  $("#storageUpdateError").textContent = "";
  $("#saveStorageUpdateButton").disabled = true;
  try {
    const result = await api("/api/reports/" + encodeURIComponent(selectedStorageReportId) + "/storage", {
      method: "POST",
      body: {
        storage_location: storageLocation,
        note: $("#storageUpdateNote").value.trim() || null
      }
    });
    $("#storageUpdateDialog").close();
    selectedStorageReportId = null;
    showToast(result.message, false);
    await loadOffice();
  } catch (error) {
    $("#storageUpdateError").textContent = error.message;
  } finally {
    $("#saveStorageUpdateButton").disabled = false;
  }
}

async function openCloseReport(reportId, reportType) {
  selectedCloseReportId = reportId;
  selectedCloseReportType = reportType;
  $("#closeReportError").textContent = "";
  $("#closeReportNote").value = "";
  const isFound = reportType === "found";
  $("#closeReportDialogTitle").textContent = isFound ? "Withdraw found report" : "Close lost report";
  $("#closeReportDescription").textContent = isFound
    ? "Withdraw this report only if you have not yet handed the physical item to the campus office. Once staff accept it and assign a tag, contact the office instead."
    : "Close your search if you recovered the item elsewhere, no longer need to search, or submitted a duplicate. Closed reports stop generating match suggestions.";
  $("#confirmCloseReportButton").textContent = isFound ? "Withdraw report" : "Close report";
  $("#closeReportReason").innerHTML = isFound
    ? '<option value="found_report_withdrawn">I cannot deliver the item to the office</option>'
    : '<option value="recovered_elsewhere">I recovered the item elsewhere</option><option value="no_longer_searching">I no longer need to search</option><option value="duplicate">This is a duplicate report</option>';
  $("#closeReportReason").value = isFound ? "found_report_withdrawn" : "no_longer_searching";
  $("#closeReportDialog").showModal();
}

async function submitCloseReport(event) {
  event.preventDefault();
  if (!selectedCloseReportId) return;
  try {
    const result = await api("/api/reports/" + encodeURIComponent(selectedCloseReportId) + "/close", {
      method: "POST",
      body: { reason: $("#closeReportReason").value, note: $("#closeReportNote").value.trim() || null }
    });
    $("#closeReportDialog").close();
    selectedCloseReportId = null;
    selectedCloseReportType = null;
    showToast(result.message, false);
    await loadMyReports();
  } catch (error) { $("#closeReportError").textContent = error.message; }
}

async function submitClaimDispute(claimId) {
  const textarea = $('[data-dispute-reason="' + CSS.escape(claimId) + '"]');
  const reason = textarea ? textarea.value.trim() : "";
  if (reason.length < 20) {
    showToast("Please explain why the decision should be reviewed (at least 20 characters).", true);
    if (textarea) textarea.focus();
    return;
  }
  try {
    const result = await api("/api/claims/" + encodeURIComponent(claimId) + "/dispute", {
      method: "POST", body: { reason }
    });
    showToast(result.message, false);
    await loadMyClaims();
  } catch (error) { showToast(error.message, true); }
}

function openHandoverDialog(claimId, itemTitle) {
  selectedHandoverClaimId = claimId;
  $("#handoverSummary").textContent = "Before releasing " + itemTitle + ", read the physical label and compare it with the Tag ID in the office record.";
  $("#handoverTag").value = "";
  $("#handoverIdentityChecked").checked = false;
  $("#handoverPhysicalChecked").checked = false;
  $("#handoverNote").value = "";
  $("#handoverError").textContent = "";
  $("#confirmHandoverButton").disabled = false;
  $("#handoverDialog").showModal();
  $("#handoverTag").focus();
}

async function submitHandover(event) {
  event.preventDefault();
  if (!selectedHandoverClaimId) return;
  const tagId = $("#handoverTag").value.trim();
  if (tagId.length < 4) {
    $("#handoverError").textContent = "Enter the exact physical Tag ID from the item label.";
    $("#handoverTag").focus();
    return;
  }
  if (!$("#handoverIdentityChecked").checked || !$("#handoverPhysicalChecked").checked) {
    $("#handoverError").textContent = "Confirm both the identity check and actual physical handover.";
    return;
  }
  $("#handoverError").textContent = "";
  $("#confirmHandoverButton").disabled = true;
  try {
    const result = await api("/api/claims/" + encodeURIComponent(selectedHandoverClaimId) + "/handover", {
      method: "POST",
      body: {
        tag_id: tagId,
        confirmed_physical_handover: $("#handoverPhysicalChecked").checked,
        claimant_identity_checked: $("#handoverIdentityChecked").checked,
        note: $("#handoverNote").value.trim() || null
      }
    });
    $("#handoverDialog").close();
    selectedHandoverClaimId = null;
    showToast(result.message, false);
    await loadOffice();
  } catch (error) {
    $("#handoverError").textContent = error.message;
  } finally {
    $("#confirmHandoverButton").disabled = false;
  }
}


function openDecisionConfirmation(claimId, action) {
  if (action === "approve") {
    const card = $('[data-claim-card="' + CSS.escape(claimId) + '"]');
    const level = Number(card && card.dataset.verificationLevel || 3);
    const minimum = Number(card && card.dataset.minimumChecks || ({1:2,2:3,3:4,4:4})[level] || 4);
    const checked = card ? $('[data-verification-check]:checked', card).map((input) => input.value) : [];
    let reason = "";
    if (checked.length < minimum) reason = "Select at least " + minimum + " distinct verification checks before verifying this claim.";
    else if (!checked.includes("claimant_identity")) reason = "Confirm the claimant's identity before verifying this claim.";
    else if (level >= 4 && !checked.includes("authorised_record")) reason = "Restricted items require the authorised-record / custodian check.";
    if (reason) {
      let message = card && card.querySelector(".field-error-note");
      if (!message && card) { message = document.createElement("p"); message.className = "field-error-note"; message.setAttribute("role","alert"); card.querySelector(".verification-checklist").appendChild(message); }
      if (message) message.textContent = reason;
      if (card) { card.scrollIntoView({behavior:"smooth",block:"center"}); card.querySelector(".verification-checklist").focus({preventScroll:true}); }
      showToast(reason, true); return;
    }
    const oldMessage=card && card.querySelector(".field-error-note"); if(oldMessage) oldMessage.remove();
  }
  const actions = {
    approve: {
      title: "Verify claim",
      button: "Verify claim",
      message: "Approve this claim only after reviewing the private evidence and completing every required verification check. The item will move to the physical handover queue."
    },
    reject: {
      title: "Reject claim",
      button: "Reject claim",
      message: "Reject this claim only after reviewing the available evidence. The claimant will be notified and may request one review."
    },
    request_more_evidence: {
      title: "Request more evidence",
      button: "Request evidence",
      message: "Ask the claimant to supply additional ownership evidence before the office makes a final decision."
    },
    mark_disputed: {
      title: "Mark claim as disputed",
      button: "Mark disputed",
      message: "Place this claim on hold. Competing claims or unresolved evidence must be reviewed before any item can be released."
    }
  };
  const actionInfo = actions[action];
  if (!actionInfo) {
    showToast("Unknown claim decision.", true);
    return;
  }
  selectedDecisionClaimId = claimId;
  selectedDecisionAction = action;
  $("#decisionConfirmTitle").textContent = actionInfo.title;
  $("#decisionConfirmMessage").textContent = actionInfo.message;
  $("#confirmDecisionButton").textContent = actionInfo.button;
  $("#confirmDecisionButton").className = "button " + (action === "reject" ? "button-danger" : "button-primary");
  $("#decisionConfirmError").textContent = "";
  $("#confirmDecisionButton").disabled = false;
  $("#decisionConfirmDialog").showModal();
}

async function submitDecision(event) {
  event.preventDefault();
  if (!selectedDecisionClaimId || !selectedDecisionAction || claimDecisionSubmitting) return;
  const claimId = selectedDecisionClaimId;
  const action = selectedDecisionAction;
  const noteInput = $('[data-note-for="' + CSS.escape(claimId) + '"]');
  const note = noteInput ? noteInput.value.trim() : "";
  const card = $('[data-claim-card="' + CSS.escape(claimId) + '"]');
  const verificationChecks = action === "approve" && card
    ? $('[data-verification-check]:checked', card).map((input) => input.value)
    : [];
  claimDecisionSubmitting = true;
  $("#confirmDecisionButton").disabled = true;
  $("#decisionConfirmError").textContent = "";
  try {
    const result = await api("/api/claims/" + encodeURIComponent(claimId) + "/decision", {
      method: "POST",
      body: { action, note: note || null, verification_checks: verificationChecks }
    });
    $("#decisionConfirmDialog").close();
    selectedDecisionClaimId = null;
    selectedDecisionAction = null;
    showToast(result.message, false);
    await loadOffice();
  } catch (error) {
    $("#decisionConfirmError").textContent = error.message;
  } finally {
    claimDecisionSubmitting = false;
    $("#confirmDecisionButton").disabled = false;
  }
}

async function start() {
  try { await loadConfig(); } catch (_) { enableMockMode(); await loadConfig(); }
  try { const data = await api("/api/me"); enterApp(data.user); return; } catch (_) {}
  if (!usingMockApi && appConfig && appConfig.demo_mode) {
    try { const demo=await api("/api/login",{method:"POST",body:{email:"student@lostlink.local",password:"student123"}}); enterApp(demo.user); showToast("Opened the student demo dashboard.",false); return; } catch (_) {}
  }
  enableMockMode(); enterApp(mockCopy(MOCK_USERS.student));
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  try {
    const result = await api("/api/login", {
      method: "POST",
      body: { email: $("#loginEmail").value.trim(), password: $("#loginPassword").value }
    });
    enterApp(result.user);
    showToast("Signed in successfully.", false);
  } catch (error) { $("#loginError").textContent = error.message; }
});

async function launchDemoAccount(email,password) {
  $("#loginError").textContent="";
  try { const result=await api("/api/login",{method:"POST",body:{email,password}}); inspectedUser=null; $("#returnToDashboardButton").classList.add("hidden"); enterApp(result.user); showToast("Opened "+(result.user.role==="office"?"office":"student")+" demo view.",false); }
  catch(error){$("#loginError").textContent=error.message;}
}
$("#fillStudent").addEventListener("click",()=>launchDemoAccount("student@lostlink.local","student123"));
$("#fillOffice").addEventListener("click",()=>launchDemoAccount("office@lostlink.local","office123"));
$("[data-demo-email]").forEach(button=>button.addEventListener("click",()=>launchDemoAccount(button.dataset.demoEmail,button.dataset.demoPassword)));
$("#viewSwitchBtn").addEventListener("click",async()=>{
 if(usingMockApi){enterApp(mockCopy(currentUser.role==="office"?MOCK_USERS.student:MOCK_USERS.office));showToast("Switched demo view. No campus records were changed by switching roles.",false);return;}
 if(!(appConfig&&appConfig.demo_mode)){showToast("Role switching is available only in the local demo. Sign in with an authorised office account to review real claims.",true);return;}
 const target=currentUser.role==="office"?{email:"student@lostlink.local",password:"student123"}:{email:"office@lostlink.local",password:"office123"};
 try{await api("/api/logout",{method:"POST"});const result=await api("/api/login",{method:"POST",body:target});enterApp(result.user);}catch(error){showToast(error.message,true);}
});
$("#showLoginButton").addEventListener("click",()=>{inspectedUser=currentUser;showLogin();$("#returnToDashboardButton").classList.toggle("hidden",!inspectedUser);});
$("#returnToDashboardButton").addEventListener("click",()=>{if(inspectedUser){const prior=inspectedUser;inspectedUser=null;enterApp(prior);}});
$("#logoutButton").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); } catch (_) {}
  inspectedUser=null; $("#returnToDashboardButton").classList.add("hidden"); showLogin();
});
$("#studentNav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) navigate(button.dataset.view);
});
document.addEventListener("click", (event) => {
  const go = event.target.closest("[data-go]");
  if (go) navigate(go.dataset.go);
  const reportKind = event.target.closest("[data-report-kind]");
  if (reportKind) setReportMode(reportKind.dataset.reportKind);
  const detailButton = event.target.closest("[data-view-details]");
  if (detailButton) openItemDetails(detailButton.dataset.viewDetails);
  const notificationMatches = event.target.closest("[data-notification-matches]");
  if (notificationMatches) {
    navigate("my-reports");
    loadMatches(notificationMatches.dataset.notificationMatches);
  }
  const matches = event.target.closest("[data-matches]");
  if (matches) loadMatches(matches.dataset.matches);
  const evidence = event.target.closest("[data-add-evidence]");
  if (evidence) openAdditionalEvidence(evidence.dataset.addEvidence);
  const dispute = event.target.closest("[data-dispute-claim]");
  if (dispute) submitClaimDispute(dispute.dataset.disputeClaim);
  const closeReport = event.target.closest("[data-close-report]");
  if (closeReport) openCloseReport(closeReport.dataset.closeReport, closeReport.dataset.closeType);
  const decision = event.target.closest("[data-decision]");
  if (decision) openDecisionConfirmation(decision.dataset.claimId, decision.dataset.decision);
  const handover = event.target.closest("[data-handover]");
  if (handover) {
    const itemTitle = handover.closest(".list-card")?.querySelector("h3")?.textContent || "this item";
    openHandoverDialog(handover.dataset.handover, itemTitle);
  }
  const storageUpdate = event.target.closest("[data-storage-update]");
  if (storageUpdate) {
    const itemTitle = storageUpdate.closest(".list-card")?.querySelector("h3")?.textContent || "Tagged item";
    openStorageUpdate(storageUpdate.dataset.storageUpdate, storageUpdate.dataset.currentLocation, itemTitle);
  }
  const notification = event.target.closest("[data-notification-read]");
  if (notification) markNotificationRead(notification.dataset.notificationRead);
  const certificate = event.target.closest("[data-certificate-download]");
  if (certificate) { if (usingMockApi) mockCertificateDownload(certificate.dataset.certificateDownload); else window.location.href = "/api/certificates/" + encodeURIComponent(certificate.dataset.certificateDownload) + "/download"; }
});
$("#searchForm").addEventListener("submit", (event) => { event.preventDefault(); loadBrowse(); });
$("#readAllNotifications").addEventListener("click", markAllNotificationsRead);
$("#clearFilters").addEventListener("click", resetSearch);
$("#reportForm").addEventListener("submit", submitReport);
$("#backToReportTypes").addEventListener("click", resetReportMode);
$("#reportImage").addEventListener("change", () => {
  const file = $("#reportImage").files[0];
  $("#imageLabel").textContent = file ? file.name : "Choose a photo";
});
$("#cancelReport").addEventListener("click", () => { resetReportMode(); navigate("browse"); });
$("#claimEvidenceImage").addEventListener("change", () => {
  const file = $("#claimEvidenceImage").files[0];
  $("#claimEvidenceImageLabel").textContent = file ? file.name : "Attach one supporting photo (optional)";
});
$("#claimForm").addEventListener("submit", submitClaim);
$("#closeItemDetails").addEventListener("click", () => { $("#itemDetailsDialog").close(); selectedDetailsReportId = null; });
$("#cancelItemDetails").addEventListener("click", () => { $("#itemDetailsDialog").close(); selectedDetailsReportId = null; });
$("#itemDetailsClaimButton").addEventListener("click", () => {
  const reportId = selectedDetailsReportId;
  $("#itemDetailsDialog").close();
  selectedDetailsReportId = null;
  if (reportId) openClaim(reportId);
});
document.addEventListener("contextmenu", (event) => {
  if (event.target.closest(".item-visual img, .item-detail-photo, .evidence-image-preview img")) event.preventDefault();
});
document.addEventListener("dragstart", (event) => {
  if (event.target.matches(".item-visual img, .item-detail-photo, .evidence-image-preview img")) event.preventDefault();
});
$("#decisionConfirmForm").addEventListener("submit", submitDecision);
$("#closeDecisionConfirm").addEventListener("click", () => {
  if (claimDecisionSubmitting) return;
  $("#decisionConfirmDialog").close();
  selectedDecisionClaimId = null;
  selectedDecisionAction = null;
});
$("#cancelDecisionConfirm").addEventListener("click", () => {
  if (claimDecisionSubmitting) return;
  $("#decisionConfirmDialog").close();
  selectedDecisionClaimId = null;
  selectedDecisionAction = null;
});
$("#decisionConfirmDialog").addEventListener("cancel", (event) => {
  if (claimDecisionSubmitting) {
    event.preventDefault();
    return;
  }
  selectedDecisionClaimId = null;
  selectedDecisionAction = null;
});
$("#handoverForm").addEventListener("submit", submitHandover);
$("#closeHandover").addEventListener("click", () => { $("#handoverDialog").close(); selectedHandoverClaimId = null; });
$("#cancelHandover").addEventListener("click", () => { $("#handoverDialog").close(); selectedHandoverClaimId = null; });
$("#additionalEvidenceForm").addEventListener("submit", submitAdditionalEvidence);
$("#closeAdditionalEvidence").addEventListener("click", () => { $("#additionalEvidenceDialog").close(); selectedEvidenceClaimId = null; });
$("#cancelAdditionalEvidence").addEventListener("click", () => { $("#additionalEvidenceDialog").close(); selectedEvidenceClaimId = null; });
$("#storageUpdateForm").addEventListener("submit", submitStorageLocation);
$("#closeStorageUpdate").addEventListener("click", () => { $("#storageUpdateDialog").close(); selectedStorageReportId = null; });
$("#cancelStorageUpdate").addEventListener("click", () => { $("#storageUpdateDialog").close(); selectedStorageReportId = null; });
$("#closeReportForm").addEventListener("submit", submitCloseReport);
$("#closeCloseReport").addEventListener("click", () => { $("#closeReportDialog").close(); selectedCloseReportId = null; selectedCloseReportType = null; });
$("#cancelCloseReport").addEventListener("click", () => { $("#closeReportDialog").close(); selectedCloseReportId = null; selectedCloseReportType = null; });
$("#closeClaim").addEventListener("click", () => $("#claimDialog").close());
$("#cancelClaim").addEventListener("click", () => $("#claimDialog").close());
$("#closeMatches").addEventListener("click", () => $("#matchesPanel").classList.add("hidden"));
$("#appView").addEventListener("submit", submitIntake);
$("#browseResults").addEventListener("click", (event) => {
  const button = event.target.closest("[data-claim]");
  if (!button) return;
  const card = button.closest(".item-card");
  const ref = card.querySelector(".item-ref").textContent;
  // Keep the current browse records available to the claim dialog without exposing internal fields.
  const query = $("#filterQuery").value;
  loadReportForClaimByRef(button.dataset.claim, ref, query);
});
$("#matchResults").addEventListener("click", (event) => {
  const button = event.target.closest("[data-claim]");
  if (button) loadReportForClaimByRef(button.dataset.claim, button.closest(".item-card").querySelector(".item-ref").textContent, "");
});

async function loadReportForClaimByRef(reportId, publicRef, searchQuery) {
  try {
    const data = await api("/api/reports?" + buildQuery({ q: searchQuery || publicRef }));
    const report = data.reports.find((item) => item.id === reportId);
    if (report) {
      selectedClaimReport = report;
      showClaimDialog(report);
      return;
    }
    // A report from the match list may not match the current text filter.
    const retry = await api("/api/reports?q=" + encodeURIComponent(publicRef));
    const found = retry.reports.find((item) => item.id === reportId);
    if (!found) throw new Error("This item is no longer available to claim. Refresh the list.");
    selectedClaimReport = found;
    showClaimDialog(found);
  } catch (error) { showToast(error.message, true); }
}

start();
