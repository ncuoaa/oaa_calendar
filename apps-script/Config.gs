// Edit this file to reuse the app for another set of calendars.
const DEFAULT_CONFIG_ = {
  title: '教務處主管行程查詢',
  timeZone: 'Asia/Taipei',
  maxRangeDays: 367,
  sessionHours: 8,
  holidayDates: ['2026-12-25'],
  notes: [
    '教務長及副教務長的行程確認及建檔，可洽：子寧(57104)、秘書(57101)、慧甄(57100)。',
    '含各組主管與會的行程確認及建檔，必須洽：秘書(57101)。',
  ],
  people: [
    {id:'dean',title:'教務長',calendarId:'deanoaa2018@gmail.com',email:'deanoaa2018@gmail.com'},
    {id:'deputy',title:'副教務長',calendarId:'oaancu2017@gmail.com',email:'oaancu2017@gmail.com'},
    {id:'registrar',title:'註冊組長',calendarId:'teyuan@gmail.com',email:'teyuan@gmail.com'},
    {id:'course',title:'課務組長',calendarId:'bkchang@g.ncu.edu.tw',email:'bkchang@g.ncu.edu.tw'},
    {id:'development',title:'教發中心主任',calendarId:'ziyang.ccu@gmail.com',email:'ziyang.ccu@gmail.com'},
    {id:'admissions',title:'招生組長',calendarId:'takee1016@gmail.com',email:'takee1016@gmail.com'},
  ],
};

function clientConfig_() {
  return {
    title: DEFAULT_CONFIG_.title,
    notes: DEFAULT_CONFIG_.notes,
    people: DEFAULT_CONFIG_.people.map(function(person) {
      return {id:person.id,title:person.title,email:person.email};
    }),
  };
}
