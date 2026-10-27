# 1
	The release failed for many reasons:
	1. It is a rolling deployment, if you dropped the old column first, how could an old instance to read data.
	2. When user change name, it may hit an old instance and write in old column. Then when the system read name, it may hit a new instance and can't get the name which user has already changed.
	The best way is :
		Add new column and copy the old value to new column.
		When we need to write the name, write both new and old column at the same time. So no matter which instance excute the read, it could get the new name.
		After rolling deloyment finished, we could stop the double write.
		After the update run for few time and everything is ok, we could concern to drop the old column.
# 2
	Reducing Cache TTL only change a big problem to a small problem. The main problem is when A want to write Active, it doesn't know B revoked it. Reducing TTL will also make cache useless. 
	A good way to solve this problem is adding a version id(which could only increase) and a flag in the database. 
	When we revoke the certificate, after write the db, we should also update the cache. So if A finish first, we will update cache again and then we could use the flag to ignore the status of certificate. If B finish first, A will find out that its version smaller than B, so it can not update the cache and nothing happen.
# 3
	Service A has 50 request workers and Service B has a 100 ms timeout. The latency usualy is 20ms, 1/ 0.02  = 50 requests per second, and 50 workers mean that ther system could handle 2500 requests per second(that's why it could handle a 1000 requests per second). Yet something bad happened,  the latency became 2s, which will definitely hit the timeout. B will retry 3 times, we could assume all of the service B retry 3 times, which could cost 100 * (3 + 1) = 400 ms. So, in the worst situation, 1 worker could only handle 1/ 0.4s = 2.5 request per second. That's 125 requests per second, but the traffic remains 1000 requests per second, and Service A stucked, for Service B can't work now.
	To solve this problem, we need to redesign the /Report endpoint. I have some ideas here:
		1. We could design /Report as a asynchromous queue (Use a few instances to handle /Report requests specifically), and set a limit to it. If the queue hit its limit, we could tell the user as soon as possible by a response.
		2. We could build a circuit break system for the service B. By using a mobile window to count the timeout and failure in a period of time, if it hit a limit, stop sending request to it (and could add a eamail or calling to ask human for help, but now a days, may we could ask a agent for help first).
	Return:
		/Report is ok, service B is ok, everything is ok: 200 and the response body.
		Service B is ok, yet /Report's queue is full: 503 + the queue is full! Please try again later
		Service B timeout: 503 + service B timeout!
		Service B circuit break: 503 + service B circuit break!
		/Report and Service A's error: As usual